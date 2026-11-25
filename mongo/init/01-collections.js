// MongoDB collections for ScholarQL, with $jsonSchema validation (contract 4).
//
// Runs automatically on the first start of the mongodb container (empty volume), via
// /docker-entrypoint-initdb.d. Safe to re-run: existing collections get the latest validator.
//   Local:  see mongo/README.md for the docker compose exec command
//   Atlas:  mongosh "<atlas-uri>" mongo/init/01-collections.js
//
// IDs are OpenAlex short IDs as strings ("W2741809807", "A5023651", "S4306420609"), exactly the
// text primary keys in A's PostgreSQL tables, so results join across the two databases as-is.
// Vector search indexes are defined in mongo/vector-indexes.json, not here.

const DB_NAME = (typeof process !== "undefined" && process.env.MONGODB_DB) || "scholarql";
const target = db.getSiblingDB(DB_NAME);

const ID = { bsonType: "string", minLength: 1 };
const OPTIONAL_ID = { bsonType: ["string", "null"] };
const EMBEDDING = {
  bsonType: "array",
  minItems: 384,
  maxItems: 384,
  items: { bsonType: "double" },
  description: "BAAI/bge-small-en-v1.5 vector, 384 floats",
};

const collections = {
  // One document per paper: the text that doesn't belong in PostgreSQL, plus its vector.
  // year and venue_id are copied from PostgreSQL so vector search can pre-filter on them.
  paper_content: {
    bsonType: "object",
    required: ["_id", "abstract", "year"],
    properties: {
      _id: { ...ID, description: "paper_id" },
      abstract: { bsonType: "string" },
      tldr: { bsonType: ["string", "null"] },
      embedding: EMBEDDING, // absent until the embedding job has run
      year: { bsonType: ["int", "long"], minimum: 1900, maximum: 2100 },
      venue_id: OPTIONAL_ID,
    },
  },

  // One document per author: a profile vector (mean of their papers' vectors) for the
  // reviewer finder. paper_ids is embedded because it's small and always read with the profile.
  author_profiles: {
    bsonType: "object",
    required: ["_id", "name", "paper_ids"],
    properties: {
      _id: { ...ID, description: "author_id" },
      name: { bsonType: "string" },
      institution_id: OPTIONAL_ID,
      embedding: EMBEDDING,
      paper_ids: { bsonType: "array", items: ID },
    },
  },

  // One document per question asked. The listed fields are guaranteed; extra fields
  // (e.g. attempts, error details) are allowed because log shapes evolve.
  query_logs: {
    bsonType: "object",
    required: ["question", "route", "ok", "latency_ms", "created_at"],
    properties: {
      question: { bsonType: "string" },
      sql: { bsonType: ["string", "null"] },
      route: { enum: ["sql", "semantic", "hybrid"] },
      ok: { bsonType: "bool", description: "false if the engine failed to answer" },
      latency_ms: { bsonType: ["int", "long", "double"], minimum: 0 },
      error: { bsonType: ["string", "null"], description: "failure reason when ok is false" },
      feedback: {
        bsonType: ["object", "null"],
        required: ["correct", "created_at"],
        properties: {
          correct: { bsonType: "bool" },
          comment: { bsonType: ["string", "null"] },
          created_at: { bsonType: "date" },
        },
      },
      created_at: { bsonType: "date" },
    },
  },
};

const existing = new Set(target.getCollectionNames());
for (const [name, schema] of Object.entries(collections)) {
  const validator = { $jsonSchema: schema };
  if (existing.has(name)) {
    target.runCommand({ collMod: name, validator, validationLevel: "strict", validationAction: "error" });
    print(`updated validator: ${DB_NAME}.${name}`);
  } else {
    target.createCollection(name, { validator, validationLevel: "strict", validationAction: "error" });
    print(`created: ${DB_NAME}.${name}`);
  }
}

// Regular (non-vector) indexes for the analytics pipelines and reviewer lookups
target.query_logs.createIndex({ created_at: -1 });
target.query_logs.createIndex({ route: 1, created_at: -1 });
target.author_profiles.createIndex({ paper_ids: 1 });
print("indexes ok");
