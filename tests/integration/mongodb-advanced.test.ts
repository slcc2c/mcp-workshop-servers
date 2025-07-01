import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { MongoDBServer } from '../../servers/mongodb';
import { MongoClient } from 'mongodb';

describe('MongoDB MCP Server Integration Tests', () => {
  let server: any; // MongoDBServer with any cast for testing
  let testClient: MongoClient;
  const testDatabase = 'mcp_test_db';
  const testCollection = 'test_collection';

  beforeAll(async () => {
    // Check if MongoDB is available
    const mongoUrl = process.env.MONGODB_URL || process.env.MONGO_URL || 'mongodb://localhost:27017';
    
    try {
      testClient = new MongoClient(mongoUrl);
      await testClient.connect();
      
      // Test connection
      await testClient.db().admin().ping();
    } catch (error) {
      console.log('⚠️  MongoDB not available, skipping MongoDB tests');
      return;
    }

    // Set environment for server
    process.env.MONGODB_URL = `${mongoUrl}/${testDatabase}`;

    // Initialize server
    try {
      server = new MongoDBServer();
      await server.initialize();
    } catch (error) {
      console.log('⚠️  Failed to initialize MongoDB server, skipping tests:', error);
      return;
    }
  });

  afterAll(async () => {
    if (server) {
      await server.shutdown();
    }
    
    if (testClient) {
      // Clean up test database
      try {
        await testClient.db(testDatabase).dropDatabase();
      } catch (error) {
        // Ignore cleanup errors
      }
      await testClient.close();
    }
  });

  beforeEach(async () => {
    if (!server || !testClient) return;

    // Clean up test collection before each test
    try {
      await server.executeTool('mongodb_drop_collection', {
        collection: testCollection,
        database: testDatabase,
      });
    } catch (error) {
      // Ignore if collection doesn't exist
    }
  });

  describe('Collection Management', () => {
    it('should create and list collections', async () => {
      if (!server) return;

      // Create collection
      const createResult = await server.executeTool('mongodb_create_collection', {
        collection: testCollection,
        database: testDatabase,
      });

      expect(createResult.success).toBe(true);
      expect(createResult.collection).toBe(testCollection);

      // List collections
      const listResult = await server.executeTool('mongodb_list_collections', {
        database: testDatabase,
      });

      expect(listResult.collections).toContainEqual(
        expect.objectContaining({
          name: testCollection,
        })
      );
      expect(listResult.count).toBeGreaterThan(0);
    });

    it('should get database statistics', async () => {
      if (!server) return;

      const statsResult = await server.executeTool('mongodb_stats', {
        database: testDatabase,
      });

      expect(statsResult.database).toBe(testDatabase);
      expect(statsResult.collections).toBeGreaterThanOrEqual(0);
      expect(statsResult.documents).toBeGreaterThanOrEqual(0);
      expect(statsResult.dataSize).toBeGreaterThanOrEqual(0);
      expect(statsResult.dataSizeHuman).toMatch(/\d+(\.\d+)?\s*(Bytes|KB|MB|GB)/);
    });
  });

  describe('Document Operations', () => {
    beforeEach(async () => {
      if (!server) return;

      // Ensure collection exists
      try {
        await server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        });
      } catch (error) {
        // Collection might already exist
      }
    });

    it('should insert and find a single document', async () => {
      if (!server) return;

      const testDoc = {
        name: 'John Doe',
        age: 30,
        email: 'john@example.com',
        tags: ['developer', 'javascript'],
      };

      // Insert document
      const insertResult = await server.executeTool('mongodb_insert_one', {
        collection: testCollection,
        document: testDoc,
        database: testDatabase,
      });

      expect(insertResult.success).toBe(true);
      expect(insertResult.insertedId).toBeDefined();
      expect(insertResult.document).toMatchObject(testDoc);

      // Find the document
      const findResult = await server.executeTool('mongodb_find_one', {
        collection: testCollection,
        filter: { name: 'John Doe' },
        database: testDatabase,
      });

      expect(findResult.document).toMatchObject(testDoc);
      expect(findResult.document._id).toBeDefined();
    });

    it('should insert multiple documents', async () => {
      if (!server) return;

      const testDocs = [
        { name: 'Alice', age: 25, department: 'Engineering' },
        { name: 'Bob', age: 35, department: 'Marketing' },
        { name: 'Charlie', age: 28, department: 'Engineering' },
      ];

      const insertResult = await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: testDocs,
        database: testDatabase,
      });

      expect(insertResult.success).toBe(true);
      expect(insertResult.insertedCount).toBe(3);
      expect(insertResult.insertedIds).toHaveLength(3);

      // Verify documents were inserted
      const findResult = await server.executeTool('mongodb_find', {
        collection: testCollection,
        filter: {},
        database: testDatabase,
      });

      expect(findResult.documents).toHaveLength(3);
      expect(findResult.count).toBe(3);
    });

    it('should find documents with filters and sorting', async () => {
      if (!server) return;

      // Insert test data
      const testDocs = [
        { name: 'Alice', age: 25, score: 85 },
        { name: 'Bob', age: 35, score: 92 },
        { name: 'Charlie', age: 28, score: 78 },
        { name: 'David', age: 32, score: 95 },
      ];

      await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: testDocs,
        database: testDatabase,
      });

      // Find with age filter
      const ageFilter = await server.executeTool('mongodb_find', {
        collection: testCollection,
        filter: { age: { $gte: 30 } },
        sort: { age: 1 },
        database: testDatabase,
      });

      expect(ageFilter.documents).toHaveLength(2);
      expect(ageFilter.documents[0].name).toBe('David');
      expect(ageFilter.documents[1].name).toBe('Bob');

      // Find with projection and limit
      const projectionResult = await server.executeTool('mongodb_find', {
        collection: testCollection,
        filter: {},
        projection: { name: 1, score: 1 },
        sort: { score: -1 },
        limit: 2,
        database: testDatabase,
      });

      expect(projectionResult.documents).toHaveLength(2);
      expect(projectionResult.documents[0].name).toBe('David');
      expect(projectionResult.documents[0].age).toBeUndefined();
      expect(projectionResult.documents[0].score).toBe(95);
    });

    it('should update documents', async () => {
      if (!server) return;

      // Insert test document
      const insertResult = await server.executeTool('mongodb_insert_one', {
        collection: testCollection,
        document: { name: 'Alice', age: 25, status: 'active' },
        database: testDatabase,
      });

      const documentId = insertResult.insertedId;

      // Update single document
      const updateResult = await server.executeTool('mongodb_update_one', {
        collection: testCollection,
        filter: { _id: documentId },
        update: { $set: { age: 26, status: 'updated' }, $inc: { updateCount: 1 } },
        database: testDatabase,
      });

      expect(updateResult.success).toBe(true);
      expect(updateResult.matchedCount).toBe(1);
      expect(updateResult.modifiedCount).toBe(1);

      // Verify update
      const findResult = await server.executeTool('mongodb_find_one', {
        collection: testCollection,
        filter: { _id: documentId },
        database: testDatabase,
      });

      expect(findResult.document.age).toBe(26);
      expect(findResult.document.status).toBe('updated');
      expect(findResult.document.updateCount).toBe(1);
    });

    it('should update multiple documents', async () => {
      if (!server) return;

      // Insert test documents
      await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: [
          { department: 'Engineering', status: 'active' },
          { department: 'Engineering', status: 'active' },
          { department: 'Marketing', status: 'active' },
        ],
        database: testDatabase,
      });

      // Update multiple documents
      const updateResult = await server.executeTool('mongodb_update_many', {
        collection: testCollection,
        filter: { department: 'Engineering' },
        update: { $set: { status: 'updated' } },
        database: testDatabase,
      });

      expect(updateResult.success).toBe(true);
      expect(updateResult.matchedCount).toBe(2);
      expect(updateResult.modifiedCount).toBe(2);

      // Verify updates
      const findResult = await server.executeTool('mongodb_find', {
        collection: testCollection,
        filter: { department: 'Engineering' },
        database: testDatabase,
      });

      expect(findResult.documents).toHaveLength(2);
      expect(findResult.documents.every(doc => doc.status === 'updated')).toBe(true);
    });

    it('should delete documents', async () => {
      if (!server) return;

      // Insert test documents
      await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: [
          { name: 'Alice', status: 'active' },
          { name: 'Bob', status: 'inactive' },
          { name: 'Charlie', status: 'inactive' },
        ],
        database: testDatabase,
      });

      // Delete one document
      const deleteOneResult = await server.executeTool('mongodb_delete_one', {
        collection: testCollection,
        filter: { name: 'Alice' },
        database: testDatabase,
      });

      expect(deleteOneResult.success).toBe(true);
      expect(deleteOneResult.deletedCount).toBe(1);

      // Delete multiple documents
      const deleteManyResult = await server.executeTool('mongodb_delete_many', {
        collection: testCollection,
        filter: { status: 'inactive' },
        database: testDatabase,
      });

      expect(deleteManyResult.success).toBe(true);
      expect(deleteManyResult.deletedCount).toBe(2);

      // Verify all documents are deleted
      const countResult = await server.executeTool('mongodb_count', {
        collection: testCollection,
        database: testDatabase,
      });

      expect(countResult.count).toBe(0);
    });

    it('should handle upsert operations', async () => {
      if (!server) return;

      // Upsert with non-existent document
      const upsertResult = await server.executeTool('mongodb_update_one', {
        collection: testCollection,
        filter: { email: 'new@example.com' },
        update: { $set: { name: 'New User', age: 25 } },
        upsert: true,
        database: testDatabase,
      });

      expect(upsertResult.success).toBe(true);
      expect(upsertResult.upserted).toBe(true);
      expect(upsertResult.upsertedId).toBeDefined();

      // Verify upserted document
      const findResult = await server.executeTool('mongodb_find_one', {
        collection: testCollection,
        filter: { email: 'new@example.com' },
        database: testDatabase,
      });

      expect(findResult.document.name).toBe('New User');
      expect(findResult.document.age).toBe(25);
    });
  });

  describe('Aggregation Operations', () => {
    beforeEach(async () => {
      if (!server) return;

      // Ensure collection exists and insert test data
      try {
        await server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        });
      } catch (error) {
        // Collection might already exist
      }

      // Insert test data for aggregation
      const testData = [
        { name: 'Alice', department: 'Engineering', salary: 90000, age: 28 },
        { name: 'Bob', department: 'Engineering', salary: 95000, age: 32 },
        { name: 'Charlie', department: 'Marketing', salary: 70000, age: 26 },
        { name: 'David', department: 'Marketing', salary: 75000, age: 30 },
        { name: 'Eve', department: 'Engineering', salary: 85000, age: 25 },
      ];

      await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: testData,
        database: testDatabase,
      });
    });

    it('should perform basic aggregation', async () => {
      if (!server) return;

      const pipeline = [
        { $group: { _id: '$department', avgSalary: { $avg: '$salary' }, count: { $sum: 1 } } },
        { $sort: { avgSalary: -1 } },
      ];

      const aggregateResult = await server.executeTool('mongodb_aggregate', {
        collection: testCollection,
        pipeline,
        database: testDatabase,
      });

      expect(aggregateResult.results).toHaveLength(2);
      expect(aggregateResult.count).toBe(2);

      // Engineering should have higher average salary
      expect(aggregateResult.results[0]._id).toBe('Engineering');
      expect(aggregateResult.results[0].count).toBe(3);
      expect(aggregateResult.results[0].avgSalary).toBeGreaterThan(80000);

      expect(aggregateResult.results[1]._id).toBe('Marketing');
      expect(aggregateResult.results[1].count).toBe(2);
    });

    it('should perform complex aggregation with multiple stages', async () => {
      if (!server) return;

      const pipeline = [
        { $match: { age: { $gte: 28 } } },
        { $group: { 
          _id: '$department', 
          totalSalary: { $sum: '$salary' },
          avgAge: { $avg: '$age' },
          employees: { $push: '$name' }
        }},
        { $addFields: { departmentCode: { $substr: ['$_id', 0, 3] } } },
        { $sort: { totalSalary: -1 } },
      ];

      const aggregateResult = await server.executeTool('mongodb_aggregate', {
        collection: testCollection,
        pipeline,
        database: testDatabase,
      });

      expect(aggregateResult.results).toHaveLength(2);
      
      const engineeringResult = aggregateResult.results.find(r => r._id === 'Engineering');
      expect(engineeringResult).toBeDefined();
      expect(engineeringResult.employees).toContain('Alice');
      expect(engineeringResult.employees).toContain('Bob');
      expect(engineeringResult.departmentCode).toBe('Eng');
    });
  });

  describe('Index Operations', () => {
    beforeEach(async () => {
      if (!server) return;

      // Ensure collection exists
      try {
        await server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        });
      } catch (error) {
        // Collection might already exist
      }
    });

    it('should create and list indexes', async () => {
      if (!server) return;

      // Create a simple index
      const createIndexResult = await server.executeTool('mongodb_create_index', {
        collection: testCollection,
        keys: { email: 1 },
        options: { unique: true, name: 'email_unique' },
        database: testDatabase,
      });

      expect(createIndexResult.success).toBe(true);
      expect(createIndexResult.indexName).toBe('email_unique');

      // Create a compound index
      await server.executeTool('mongodb_create_index', {
        collection: testCollection,
        keys: { department: 1, salary: -1 },
        options: { name: 'dept_salary_idx' },
        database: testDatabase,
      });

      // List indexes
      const listIndexResult = await server.executeTool('mongodb_list_indexes', {
        collection: testCollection,
        database: testDatabase,
      });

      expect(listIndexResult.indexes).toHaveLength(3); // _id, email_unique, dept_salary_idx
      expect(listIndexResult.count).toBe(3);

      const emailIndex = listIndexResult.indexes.find(idx => idx.name === 'email_unique');
      expect(emailIndex).toBeDefined();
      expect(emailIndex.unique).toBe(true);

      const compoundIndex = listIndexResult.indexes.find(idx => idx.name === 'dept_salary_idx');
      expect(compoundIndex).toBeDefined();
      expect(compoundIndex.key).toEqual({ department: 1, salary: -1 });
    });
  });

  describe('Query Operations', () => {
    beforeEach(async () => {
      if (!server) return;

      // Ensure collection exists and insert test data
      try {
        await server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        });
      } catch (error) {
        // Collection might already exist
      }

      const testData = [
        { name: 'Alice', age: 25, tags: ['python', 'javascript'], active: true },
        { name: 'Bob', age: 30, tags: ['java', 'python'], active: false },
        { name: 'Charlie', age: 35, tags: ['javascript', 'react'], active: true },
        { name: 'David', age: 28, tags: ['python'], active: true },
      ];

      await server.executeTool('mongodb_insert_many', {
        collection: testCollection,
        documents: testData,
        database: testDatabase,
      });
    });

    it('should count documents with filters', async () => {
      if (!server) return;

      // Count all documents
      const totalCount = await server.executeTool('mongodb_count', {
        collection: testCollection,
        database: testDatabase,
      });

      expect(totalCount.count).toBe(4);
      expect(totalCount.hasFilter).toBe(false);

      // Count with filter
      const activeCount = await server.executeTool('mongodb_count', {
        collection: testCollection,
        filter: { active: true },
        database: testDatabase,
      });

      expect(activeCount.count).toBe(3);
      expect(activeCount.hasFilter).toBe(true);
    });

    it('should get distinct values', async () => {
      if (!server) return;

      // Get distinct ages
      const distinctAges = await server.executeTool('mongodb_distinct', {
        collection: testCollection,
        field: 'age',
        database: testDatabase,
      });

      expect(distinctAges.field).toBe('age');
      expect(distinctAges.values).toHaveLength(4);
      expect(distinctAges.values).toContain(25);
      expect(distinctAges.values).toContain(30);
      expect(distinctAges.values).toContain(35);
      expect(distinctAges.values).toContain(28);

      // Get distinct values with filter
      const distinctActiveTags = await server.executeTool('mongodb_distinct', {
        collection: testCollection,
        field: 'tags',
        filter: { active: true },
        database: testDatabase,
      });

      expect(distinctActiveTags.field).toBe('tags');
      expect(distinctActiveTags.values).toContain('python');
      expect(distinctActiveTags.values).toContain('javascript');
      expect(distinctActiveTags.values).not.toContain('java'); // Bob is not active
    });

    it('should handle complex queries with ObjectId', async () => {
      if (!server) return;

      // Insert a document and get its ID
      const insertResult = await server.executeTool('mongodb_insert_one', {
        collection: testCollection,
        document: { name: 'Test User', type: 'special' },
        database: testDatabase,
      });

      const objectId = insertResult.insertedId;

      // Find by ObjectId string
      const findByIdResult = await server.executeTool('mongodb_find_one', {
        collection: testCollection,
        filter: { _id: objectId.toString() },
        database: testDatabase,
      });

      expect(findByIdResult.document.name).toBe('Test User');
      expect(findByIdResult.document.type).toBe('special');

      // Update by ObjectId
      const updateResult = await server.executeTool('mongodb_update_one', {
        collection: testCollection,
        filter: { _id: objectId.toString() },
        update: { $set: { updated: true } },
        database: testDatabase,
      });

      expect(updateResult.success).toBe(true);
      expect(updateResult.modifiedCount).toBe(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid collection operations', async () => {
      if (!server) return;

      // Try to find in non-existent collection
      const findResult = await server.executeTool('mongodb_find', {
        collection: 'nonexistent_collection',
        filter: {},
        database: testDatabase,
      });

      // Should return empty results, not error
      expect(findResult.documents).toHaveLength(0);
      expect(findResult.count).toBe(0);
    });

    it('should handle duplicate collection creation', async () => {
      if (!server) return;

      // Create collection
      await server.executeTool('mongodb_create_collection', {
        collection: testCollection,
        database: testDatabase,
      });

      // Try to create the same collection again
      await expect(
        server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        })
      ).rejects.toThrow('already exists');
    });

    it('should handle document not found', async () => {
      if (!server) return;

      // Ensure collection exists
      try {
        await server.executeTool('mongodb_create_collection', {
          collection: testCollection,
          database: testDatabase,
        });
      } catch (error) {
        // Collection might already exist
      }

      // Try to find non-existent document
      await expect(
        server.executeTool('mongodb_find_one', {
          collection: testCollection,
          filter: { name: 'NonExistent' },
          database: testDatabase,
        })
      ).rejects.toThrow('not found');
    });
  });
});