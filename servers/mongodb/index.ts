/**
 * MongoDB MCP Server
 * Provides NoSQL database operations with flexible schema support
 */

import { z } from 'zod';
import { MongoClient, Db, ObjectId, Filter, UpdateFilter, FindOptions } from 'mongodb';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const FindSchema = z.object({
  collection: z.string().describe('Collection name'),
  filter: z.record(z.any()).default({}).describe('Query filter'),
  projection: z.record(z.any()).optional().describe('Fields to include/exclude'),
  sort: z.record(z.number()).optional().describe('Sort order (1 for asc, -1 for desc)'),
  limit: z.number().optional().describe('Maximum documents to return'),
  skip: z.number().optional().describe('Number of documents to skip'),
  database: z.string().optional().describe('Database name (uses default if not specified)'),
});

const FindOneSchema = z.object({
  collection: z.string().describe('Collection name'),
  filter: z.record(z.any()).default({}).describe('Query filter'),
  projection: z.record(z.any()).optional().describe('Fields to include/exclude'),
  database: z.string().optional().describe('Database name'),
});

const InsertOneSchema = z.object({
  collection: z.string().describe('Collection name'),
  document: z.record(z.any()).describe('Document to insert'),
  database: z.string().optional().describe('Database name'),
});

const InsertManySchema = z.object({
  collection: z.string().describe('Collection name'),
  documents: z.array(z.record(z.any())).describe('Documents to insert'),
  ordered: z.boolean().default(true).describe('Whether to stop on first error'),
  database: z.string().optional().describe('Database name'),
});

const UpdateSchema = z.object({
  collection: z.string().describe('Collection name'),
  filter: z.record(z.any()).describe('Query filter'),
  update: z.record(z.any()).describe('Update operations'),
  upsert: z.boolean().default(false).describe('Insert if not found'),
  database: z.string().optional().describe('Database name'),
});

const UpdateManySchema = z.object({
  collection: z.string().describe('Collection name'),
  filter: z.record(z.any()).describe('Query filter'),
  update: z.record(z.any()).describe('Update operations'),
  upsert: z.boolean().default(false).describe('Insert if not found'),
  database: z.string().optional().describe('Database name'),
});

const DeleteSchema = z.object({
  collection: z.string().describe('Collection name'),
  filter: z.record(z.any()).describe('Query filter'),
  database: z.string().optional().describe('Database name'),
});

const AggregateSchema = z.object({
  collection: z.string().describe('Collection name'),
  pipeline: z.array(z.record(z.any())).describe('Aggregation pipeline'),
  database: z.string().optional().describe('Database name'),
});

const CreateIndexSchema = z.object({
  collection: z.string().describe('Collection name'),
  keys: z.record(z.number()).describe('Index keys (1 for asc, -1 for desc)'),
  options: z.object({
    unique: z.boolean().optional(),
    sparse: z.boolean().optional(),
    background: z.boolean().optional(),
    name: z.string().optional(),
  }).optional().describe('Index options'),
  database: z.string().optional().describe('Database name'),
});

const CollectionSchema = z.object({
  database: z.string().optional().describe('Database name'),
});

const CreateCollectionSchema = z.object({
  collection: z.string().describe('Collection name'),
  options: z.object({
    capped: z.boolean().optional(),
    size: z.number().optional(),
    max: z.number().optional(),
  }).optional().describe('Collection options'),
  database: z.string().optional().describe('Database name'),
});

export class MongoDBServer extends BaseMCPServer {
  private client!: MongoClient;
  private defaultDatabase?: string;
  private connectionString?: string;

  constructor() {
    super('mongodb', '1.0.0', 'MongoDB NoSQL database operations');
  }

  protected async onInitialize(): Promise<void> {
    // Get connection string from environment or 1Password
    this.connectionString = process.env.MONGODB_URL || process.env.MONGO_URL;
    
    if (!this.connectionString) {
      throw new Error('MongoDB connection string not found. Set MONGODB_URL or MONGO_URL environment variable.');
    }

    // Extract default database from connection string
    const match = this.connectionString.match(/\/([^/?]+)(\?|$)/);
    this.defaultDatabase = match ? match[1] : 'test';

    // Create MongoDB client
    this.client = new MongoClient(this.connectionString, {
      maxPoolSize: 10,
      minPoolSize: 2,
      serverSelectionTimeoutMS: 5000,
    });

    // Connect to MongoDB
    await this.client.connect();
    
    // Test connection
    await this.client.db().admin().ping();
    
    this.logger.info('MongoDB server initialized', {
      defaultDatabase: this.defaultDatabase,
    });
  }

  protected async onShutdown(): Promise<void> {
    await this.client.close();
    this.logger.info('MongoDB connection closed');
  }

  private getDatabase(dbName?: string): Db {
    return this.client.db(dbName || this.defaultDatabase);
  }

  private convertIdFields(doc: any): any {
    if (doc && typeof doc === 'object') {
      // Convert _id strings to ObjectId
      if (doc._id && typeof doc._id === 'string' && ObjectId.isValid(doc._id)) {
        doc._id = new ObjectId(doc._id);
      }
      
      // Convert $oid format
      if (doc._id && doc._id.$oid) {
        doc._id = new ObjectId(doc._id.$oid);
      }
    }
    return doc;
  }

  private convertFilter(filter: any): Filter<any> {
    const converted = { ...filter };
    
    // Convert _id strings to ObjectId
    if (converted._id) {
      if (typeof converted._id === 'string' && ObjectId.isValid(converted._id)) {
        converted._id = new ObjectId(converted._id);
      } else if (converted._id.$oid) {
        converted._id = new ObjectId(converted._id.$oid);
      }
    }
    
    // Convert operators
    Object.keys(converted).forEach(key => {
      if (typeof converted[key] === 'object' && converted[key] !== null) {
        // Handle $in operator with ObjectIds
        if (converted[key].$in && Array.isArray(converted[key].$in)) {
          converted[key].$in = converted[key].$in.map((id: any) => {
            if (key === '_id' && typeof id === 'string' && ObjectId.isValid(id)) {
              return new ObjectId(id);
            }
            return id;
          });
        }
      }
    });
    
    return converted;
  }

  protected async registerTools(): Promise<void> {
    // Find documents
    this.registerTool(
      'mongodb_find',
      'Find documents in a collection',
      FindSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const options: FindOptions = {};
        
        if (params.projection) options.projection = params.projection;
        if (params.sort) options.sort = params.sort;
        if (params.limit) options.limit = params.limit;
        if (params.skip) options.skip = params.skip;
        
        const cursor = collection.find(filter, options);
        const documents = await cursor.toArray();
        const count = await collection.countDocuments(filter);
        
        return {
          documents,
          count,
          hasMore: params.limit ? count > (params.skip || 0) + params.limit : false,
        };
      })
    );

    // Find one document
    this.registerTool(
      'mongodb_find_one',
      'Find a single document',
      FindOneSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const options: FindOptions = {};
        
        if (params.projection) options.projection = params.projection;
        
        const document = await collection.findOne(filter, options);
        
        if (!document) {
          throw new ResourceNotFoundError('Document not found');
        }
        
        return { document };
      })
    );

    // Insert one document
    this.registerTool(
      'mongodb_insert_one',
      'Insert a single document',
      InsertOneSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const document = this.convertIdFields(params.document);
        const result = await collection.insertOne(document);
        
        return {
          success: result.acknowledged,
          insertedId: result.insertedId,
          document: { ...document, _id: result.insertedId },
        };
      })
    );

    // Insert many documents
    this.registerTool(
      'mongodb_insert_many',
      'Insert multiple documents',
      InsertManySchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const documents = params.documents.map((doc: any) => this.convertIdFields(doc));
        const result = await collection.insertMany(documents, {
          ordered: params.ordered,
        });
        
        return {
          success: result.acknowledged,
          insertedCount: result.insertedCount,
          insertedIds: Object.values(result.insertedIds),
        };
      })
    );

    // Update one document
    this.registerTool(
      'mongodb_update_one',
      'Update a single document',
      UpdateSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const update = params.update as UpdateFilter<any>;
        
        const result = await collection.updateOne(filter, update, {
          upsert: params.upsert,
        });
        
        return {
          success: result.acknowledged,
          matchedCount: result.matchedCount,
          modifiedCount: result.modifiedCount,
          upsertedId: result.upsertedId,
          upserted: result.upsertedCount > 0,
        };
      })
    );

    // Update many documents
    this.registerTool(
      'mongodb_update_many',
      'Update multiple documents',
      UpdateManySchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const update = params.update as UpdateFilter<any>;
        
        const result = await collection.updateMany(filter, update, {
          upsert: params.upsert,
        });
        
        return {
          success: result.acknowledged,
          matchedCount: result.matchedCount,
          modifiedCount: result.modifiedCount,
          upsertedId: result.upsertedId,
          upserted: result.upsertedCount > 0,
        };
      })
    );

    // Delete one document
    this.registerTool(
      'mongodb_delete_one',
      'Delete a single document',
      DeleteSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const result = await collection.deleteOne(filter);
        
        return {
          success: result.acknowledged,
          deletedCount: result.deletedCount,
        };
      })
    );

    // Delete many documents
    this.registerTool(
      'mongodb_delete_many',
      'Delete multiple documents',
      DeleteSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const result = await collection.deleteMany(filter);
        
        return {
          success: result.acknowledged,
          deletedCount: result.deletedCount,
        };
      })
    );

    // Aggregate
    this.registerTool(
      'mongodb_aggregate',
      'Run aggregation pipeline',
      AggregateSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const cursor = collection.aggregate(params.pipeline);
        const results = await cursor.toArray();
        
        return {
          results,
          count: results.length,
        };
      })
    );

    // Create index
    this.registerTool(
      'mongodb_create_index',
      'Create an index on a collection',
      CreateIndexSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const indexName = await collection.createIndex(params.keys, params.options || {});
        
        return {
          success: true,
          indexName,
          keys: params.keys,
        };
      })
    );

    // List indexes
    this.registerTool(
      'mongodb_list_indexes',
      'List all indexes on a collection',
      z.object({
        database: z.string().optional().describe('Database name'),
        collection: z.string().describe('Collection name'),
      }),
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const indexes = await collection.indexes();
        
        return {
          indexes,
          count: indexes.length,
        };
      })
    );

    // List collections
    this.registerTool(
      'mongodb_list_collections',
      'List all collections in a database',
      CollectionSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collections = await db.listCollections().toArray();
        
        return {
          collections: collections.map(c => ({
            name: c.name,
            type: c.type,
            options: (c as any).options,
          })),
          count: collections.length,
        };
      })
    );

    // Create collection
    this.registerTool(
      'mongodb_create_collection',
      'Create a new collection',
      CreateCollectionSchema,
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        
        try {
          await db.createCollection(params.collection, params.options || {});
          
          return {
            success: true,
            collection: params.collection,
            database: db.databaseName,
          };
        } catch (error: any) {
          if (error.code === 48) { // Collection already exists
            throw new InvalidParamsError(`Collection "${params.collection}" already exists`);
          }
          throw error;
        }
      })
    );

    // Drop collection
    this.registerTool(
      'mongodb_drop_collection',
      'Drop a collection',
      z.object({
        database: z.string().optional().describe('Database name'),
        collection: z.string().describe('Collection name'),
      }),
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const result = await db.dropCollection(params.collection);
        
        return {
          success: result,
          collection: params.collection,
          database: db.databaseName,
        };
      })
    );

    // Database stats
    this.registerTool(
      'mongodb_stats',
      'Get database statistics',
      z.object({
        database: z.string().optional().describe('Database name'),
      }),
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const stats = await db.stats();
        
        return {
          database: db.databaseName,
          collections: stats.collections,
          documents: stats.objects,
          dataSize: stats.dataSize,
          storageSize: stats.storageSize,
          indexes: stats.indexes,
          indexSize: stats.indexSize,
          dataSizeHuman: this.formatBytes(stats.dataSize),
          storageSizeHuman: this.formatBytes(stats.storageSize),
        };
      })
    );

    // Count documents
    this.registerTool(
      'mongodb_count',
      'Count documents in a collection',
      z.object({
        database: z.string().optional().describe('Database name'),
        collection: z.string().describe('Collection name'),
        filter: z.record(z.any()).default({}).describe('Query filter'),
      }),
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const count = await collection.countDocuments(filter);
        
        return {
          count,
          collection: params.collection,
          hasFilter: Object.keys(params.filter).length > 0,
        };
      })
    );

    // Distinct values
    this.registerTool(
      'mongodb_distinct',
      'Get distinct values for a field',
      z.object({
        database: z.string().optional().describe('Database name'),
        collection: z.string().describe('Collection name'),
        field: z.string().describe('Field name to get distinct values for'),
        filter: z.record(z.any()).default({}).describe('Query filter'),
      }),
      createToolHandler<any>(async (params) => {
        const db = this.getDatabase(params.database);
        const collection = db.collection(params.collection);
        
        const filter = this.convertFilter(params.filter);
        const values = await collection.distinct(params.field, filter);
        
        return {
          field: params.field,
          values,
          count: values.length,
        };
      })
    );
  }

  private formatBytes(bytes: number): string {
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    if (bytes === 0) return '0 Bytes';
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  }
}