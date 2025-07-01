import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { PostgreSQLServer } from '../../servers/postgresql';
import { Pool } from 'pg';

describe('PostgreSQL MCP Server Integration Tests', () => {
  let server: any; // PostgreSQLServer with any cast for testing
  let testPool: Pool;
  const testDatabase = 'test_mcp';
  const testTable = 'test_users';

  beforeAll(async () => {
    // Set up test database connection
    process.env.POSTGRES_URL = process.env.POSTGRES_URL || 'postgresql://localhost:5432/postgres';
    
    // Create test database
    testPool = new Pool({
      connectionString: process.env.POSTGRES_URL,
    });

    try {
      await testPool.query(`DROP DATABASE IF EXISTS ${testDatabase}`);
      await testPool.query(`CREATE DATABASE ${testDatabase}`);
    } catch (error) {
      console.error('Failed to create test database:', error);
    }

    // Update connection string to use test database
    const baseUrl = process.env.POSTGRES_URL.replace(/\/[^/]+$/, '');
    process.env.POSTGRES_URL = `${baseUrl}/${testDatabase}`;

    // Initialize server
    server = new PostgreSQLServer();
    await server.initialize();
  });

  afterAll(async () => {
    // Clean up
    await server.shutdown();
    
    // Drop test database
    try {
      await testPool.query(`DROP DATABASE IF EXISTS ${testDatabase}`);
    } catch (error) {
      console.error('Failed to drop test database:', error);
    }
    
    await testPool.end();
  });

  beforeEach(async () => {
    // Clean up any existing test table
    try {
      await server.executeTool('postgres_query', {
        query: `DROP TABLE IF EXISTS ${testTable}`,
      });
    } catch (error) {
      // Ignore errors
    }
  });

  describe('Table Operations', () => {
    it('should create a table', async () => {
      const result = await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)', nullable: false },
          { name: 'email', type: 'VARCHAR(255)', unique: true },
          { name: 'created_at', type: 'TIMESTAMP', default: 'NOW()' },
        ],
      });

      expect(result.success).toBe(true);
      expect(result.table).toBe(testTable);
    });

    it('should list tables', async () => {
      // Create a table first
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)' },
        ],
      });

      const result = await server.executeTool('postgres_list_tables', {
        schema: 'public',
      });

      expect(result.tables).toContainEqual(
        expect.objectContaining({
          name: testTable,
          schema: 'public',
        })
      );
      expect(result.count).toBeGreaterThan(0);
    });

    it('should get table info', async () => {
      // Create a table first
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)', nullable: false },
          { name: 'age', type: 'INTEGER', nullable: true },
        ],
      });

      const result = await server.executeTool('postgres_table_info', {
        table: testTable,
      });

      expect(result.table).toBe(testTable);
      expect(result.columns).toHaveLength(3);
      expect(result.columns[0]).toMatchObject({
        name: 'id',
        nullable: false,
      });
      expect(result.columns[1]).toMatchObject({
        name: 'name',
        type: 'character varying',
        nullable: false,
      });
    });
  });

  describe('Data Operations', () => {
    beforeEach(async () => {
      // Create test table
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)', nullable: false },
          { name: 'email', type: 'VARCHAR(255)' },
          { name: 'age', type: 'INTEGER' },
        ],
      });
    });

    it('should insert data', async () => {
      const result = await server.executeTool('postgres_insert', {
        table: testTable,
        data: {
          name: 'John Doe',
          email: 'john@example.com',
          age: 30,
        },
        returning: ['id', 'name'],
      });

      expect(result.success).toBe(true);
      expect(result.rowCount).toBe(1);
      expect(result.rows[0]).toMatchObject({
        name: 'John Doe',
      });
      expect(result.rows[0].id).toBeDefined();
    });

    it('should select data', async () => {
      // Insert test data
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { name: 'Alice', email: 'alice@example.com', age: 25 },
      });
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { name: 'Bob', email: 'bob@example.com', age: 35 },
      });

      const result = await server.executeTool('postgres_select', {
        table: testTable,
        columns: ['name', 'age'],
        where: { age: 25 },
      });

      expect(result.rowCount).toBe(1);
      expect(result.rows[0]).toMatchObject({
        name: 'Alice',
        age: 25,
      });
    });

    it('should update data', async () => {
      // Insert test data
      const insertResult = await server.executeTool('postgres_insert', {
        table: testTable,
        data: { name: 'Charlie', email: 'charlie@example.com', age: 28 },
        returning: ['id'],
      });

      const id = insertResult.rows[0].id;

      const updateResult = await server.executeTool('postgres_update', {
        table: testTable,
        data: { age: 29, email: 'charlie.new@example.com' },
        where: { id },
        returning: ['id', 'age', 'email'],
      });

      expect(updateResult.success).toBe(true);
      expect(updateResult.rowCount).toBe(1);
      expect(updateResult.rows[0]).toMatchObject({
        id,
        age: 29,
        email: 'charlie.new@example.com',
      });
    });

    it('should delete data', async () => {
      // Insert test data
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { name: 'David', email: 'david@example.com', age: 40 },
      });

      const deleteResult = await server.executeTool('postgres_delete', {
        table: testTable,
        where: { name: 'David' },
        returning: ['name'],
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.rowCount).toBe(1);
      expect(deleteResult.rows[0].name).toBe('David');

      // Verify deletion
      const selectResult = await server.executeTool('postgres_select', {
        table: testTable,
        where: { name: 'David' },
      });

      expect(selectResult.rowCount).toBe(0);
    });
  });

  describe('Query Operations', () => {
    it('should execute raw queries', async () => {
      const result = await server.executeTool('postgres_query', {
        query: 'SELECT version()',
      });

      expect(result.rowCount).toBe(1);
      expect(result.rows[0].version).toContain('PostgreSQL');
    });

    it('should execute parameterized queries', async () => {
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'value', type: 'INTEGER' },
        ],
      });

      await server.executeTool('postgres_query', {
        query: `INSERT INTO ${testTable} (value) VALUES ($1), ($2), ($3)`,
        params: [10, 20, 30],
      });

      const result = await server.executeTool('postgres_query', {
        query: `SELECT SUM(value) as total FROM ${testTable} WHERE value > $1`,
        params: [15],
      });

      expect(result.rows[0].total).toBe('50'); // PostgreSQL returns numeric as string
    });
  });

  describe('Transaction Operations', () => {
    it('should execute successful transaction', async () => {
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'balance', type: 'DECIMAL(10,2)' },
        ],
      });

      // Insert initial data
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { id: 1, balance: 100 },
      });
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { id: 2, balance: 50 },
      });

      // Execute transaction
      const result = await server.executeTool('postgres_transaction', {
        queries: [
          {
            query: `UPDATE ${testTable} SET balance = balance - $1 WHERE id = $2`,
            params: [30, 1],
          },
          {
            query: `UPDATE ${testTable} SET balance = balance + $1 WHERE id = $2`,
            params: [30, 2],
          },
        ],
      });

      expect(result.success).toBe(true);
      expect(result.totalQueries).toBe(2);

      // Verify balances
      const checkResult = await server.executeTool('postgres_select', {
        table: testTable,
        orderBy: [{ column: 'id', direction: 'ASC' }],
      });

      expect(parseFloat(checkResult.rows[0].balance)).toBe(70);
      expect(parseFloat(checkResult.rows[1].balance)).toBe(80);
    });

    it('should rollback failed transaction', async () => {
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'value', type: 'INTEGER', nullable: false },
        ],
      });

      // Insert initial data
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { id: 1, value: 100 },
      });

      // Execute transaction with failing query
      await expect(
        server.executeTool('postgres_transaction', {
          queries: [
            {
              query: `UPDATE ${testTable} SET value = $1 WHERE id = $2`,
              params: [200, 1],
            },
            {
              query: `INSERT INTO ${testTable} (value) VALUES ($1)`,
              params: [null], // This will fail due to NOT NULL constraint
            },
          ],
        })
      ).rejects.toThrow();

      // Verify rollback
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { id: 1 },
      });

      expect(result.rows[0].value).toBe(100); // Original value preserved
    });
  });

  describe('Advanced Operations', () => {
    it('should handle complex select with ordering and limits', async () => {
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)' },
          { name: 'score', type: 'INTEGER' },
        ],
      });

      // Insert test data
      const names = ['Alice', 'Bob', 'Charlie', 'David', 'Eve'];
      const scores = [85, 92, 78, 95, 88];

      for (let i = 0; i < names.length; i++) {
        await server.executeTool('postgres_insert', {
          table: testTable,
          data: { name: names[i], score: scores[i] },
        });
      }

      const result = await server.executeTool('postgres_select', {
        table: testTable,
        columns: ['name', 'score'],
        where: { score: { $gte: 80 } },
        orderBy: [{ column: 'score', direction: 'DESC' }],
        limit: 3,
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('David'); // Highest score (95)
      expect(result.rows[1].name).toBe('Bob');   // Second highest (92)
      expect(result.rows[2].name).toBe('Eve');   // Third highest (88)
    });

    it('should get database statistics', async () => {
      const result = await server.executeTool('postgres_stats', {});

      expect(result.database).toBeDefined();
      expect(result.size).toBeGreaterThan(0);
      expect(result.sizeHuman).toMatch(/\d+(\.\d+)?\s*(Bytes|KB|MB|GB)/);
      expect(result.tableCount).toBeGreaterThanOrEqual(0);
      expect(result.activeConnections).toBeGreaterThanOrEqual(1);
      expect(result.poolStatus).toMatchObject({
        total: expect.any(Number),
        idle: expect.any(Number),
        waiting: expect.any(Number),
      });
    });
  });

  describe('MongoDB-style Query Operators', () => {
    beforeEach(async () => {
      // Create test table with various data types
      await server.executeTool('postgres_create_table', {
        table: testTable,
        columns: [
          { name: 'id', type: 'SERIAL', primaryKey: true },
          { name: 'name', type: 'VARCHAR(100)' },
          { name: 'age', type: 'INTEGER' },
          { name: 'score', type: 'DECIMAL(5,2)' },
          { name: 'active', type: 'BOOLEAN', default: 'true' },
          { name: 'tags', type: 'TEXT[]' },
        ],
      });

      // Insert test data
      const testData = [
        { name: 'Alice', age: 25, score: 85.5, active: true },
        { name: 'Bob', age: 30, score: 92.0, active: true },
        { name: 'Charlie', age: 35, score: 78.5, active: false },
        { name: 'David', age: 28, score: 95.0, active: true },
        { name: 'Eve', age: 32, score: 88.0, active: false },
      ];

      for (const data of testData) {
        await server.executeTool('postgres_insert', {
          table: testTable,
          data,
        });
      }
    });

    it('should handle $gte operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { age: { $gte: 30 } },
        orderBy: [{ column: 'age', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('Bob');
      expect(result.rows[1].name).toBe('Eve');
      expect(result.rows[2].name).toBe('Charlie');
    });

    it('should handle $gt operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { score: { $gt: 85.5 } },
        orderBy: [{ column: 'score', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('Eve');
      expect(result.rows[1].name).toBe('Bob');
      expect(result.rows[2].name).toBe('David');
    });

    it('should handle $lte operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { age: { $lte: 28 } },
        orderBy: [{ column: 'age', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(2);
      expect(result.rows[0].name).toBe('Alice');
      expect(result.rows[1].name).toBe('David');
    });

    it('should handle $lt operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { score: { $lt: 85.5 } },
      });

      expect(result.rowCount).toBe(1);
      expect(result.rows[0].name).toBe('Charlie');
    });

    it('should handle multiple operators on same field', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { age: { $gte: 28, $lt: 35 } },
        orderBy: [{ column: 'age', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('David');
      expect(result.rows[1].name).toBe('Bob');
      expect(result.rows[2].name).toBe('Eve');
    });

    it('should handle $ne operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { active: { $ne: true } },
        orderBy: [{ column: 'name', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(2);
      expect(result.rows[0].name).toBe('Charlie');
      expect(result.rows[1].name).toBe('Eve');
    });

    it('should handle $in operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { name: { $in: ['Alice', 'Charlie', 'Eve'] } },
        orderBy: [{ column: 'name', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('Alice');
      expect(result.rows[1].name).toBe('Charlie');
      expect(result.rows[2].name).toBe('Eve');
    });

    it('should handle $nin operator', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { name: { $nin: ['Alice', 'Bob'] } },
        orderBy: [{ column: 'name', direction: 'ASC' }],
      });

      expect(result.rowCount).toBe(3);
      expect(result.rows[0].name).toBe('Charlie');
      expect(result.rows[1].name).toBe('David');
      expect(result.rows[2].name).toBe('Eve');
    });

    it('should handle complex queries with multiple conditions', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: {
          age: { $gte: 25, $lte: 30 },
          score: { $gt: 80 },
          active: true,
        },
        orderBy: [{ column: 'score', direction: 'DESC' }],
      });

      expect(result.rowCount).toBe(2);
      expect(result.rows[0].name).toBe('Bob');
      expect(result.rows[1].name).toBe('Alice');
    });

    it('should handle operators in update queries', async () => {
      const updateResult = await server.executeTool('postgres_update', {
        table: testTable,
        data: { score: 100 },
        where: { age: { $gte: 30 } },
        returning: ['name', 'score'],
      });

      expect(updateResult.rowCount).toBe(3);
      expect(updateResult.rows).toContainEqual(
        expect.objectContaining({ name: 'Bob', score: '100' })
      );
      expect(updateResult.rows).toContainEqual(
        expect.objectContaining({ name: 'Charlie', score: '100' })
      );
      expect(updateResult.rows).toContainEqual(
        expect.objectContaining({ name: 'Eve', score: '100' })
      );
    });

    it('should handle operators in delete queries', async () => {
      const deleteResult = await server.executeTool('postgres_delete', {
        table: testTable,
        where: { score: { $lt: 85 } },
        returning: ['name'],
      });

      expect(deleteResult.rowCount).toBe(1);
      expect(deleteResult.rows[0].name).toBe('Charlie');

      // Verify remaining records
      const remaining = await server.executeTool('postgres_select', {
        table: testTable,
        orderBy: [{ column: 'name', direction: 'ASC' }],
      });

      expect(remaining.rowCount).toBe(4);
    });

    it('should handle null comparisons', async () => {
      // Insert a record with null age
      await server.executeTool('postgres_insert', {
        table: testTable,
        data: { name: 'Frank', age: null, score: 90 },
      });

      // Test IS NULL
      const nullResult = await server.executeTool('postgres_select', {
        table: testTable,
        where: { age: null },
      });

      expect(nullResult.rowCount).toBe(1);
      expect(nullResult.rows[0].name).toBe('Frank');

      // Test IS NOT NULL with $ne
      const notNullResult = await server.executeTool('postgres_select', {
        table: testTable,
        where: { age: { $ne: null } },
        orderBy: [{ column: 'name', direction: 'ASC' }],
      });

      expect(notNullResult.rowCount).toBe(5);
      expect(notNullResult.rows.map(r => r.name)).not.toContain('Frank');
    });

    it('should maintain backward compatibility with simple equality', async () => {
      const result = await server.executeTool('postgres_select', {
        table: testTable,
        where: { name: 'Alice', active: true },
      });

      expect(result.rowCount).toBe(1);
      expect(result.rows[0]).toMatchObject({
        name: 'Alice',
        age: 25,
        active: true,
      });
    });
  });
});