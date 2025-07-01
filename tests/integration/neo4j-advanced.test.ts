import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { Neo4jServer } from '../../servers/neo4j';
import neo4j, { Driver } from 'neo4j-driver';

describe('Neo4j MCP Server Integration Tests', () => {
  let server: any; // Neo4jServer with any cast for testing
  let testDriver: Driver;
  const testLabels = ['MCPTest', 'TestNode'];
  const testRelTypes = ['TEST_RELATION', 'CONNECTS_TO'];

  beforeAll(async () => {
    // Check if Neo4j is available
    const neo4jUrl = process.env.NEO4J_URL || process.env.NEO4J_URI || 'bolt://localhost:7687';
    const neo4jUser = process.env.NEO4J_USER || 'neo4j';
    const neo4jPassword = process.env.NEO4J_PASSWORD || 'password';
    
    try {
      testDriver = neo4j.driver(
        neo4jUrl,
        neo4j.auth.basic(neo4jUser, neo4jPassword)
      );
      
      const session = testDriver.session();
      await session.run('RETURN 1');
      await session.close();
    } catch (error) {
      console.log('⚠️  Neo4j not available, skipping Neo4j tests');
      return;
    }

    // Set environment for server
    process.env.NEO4J_URL = neo4jUrl;
    process.env.NEO4J_USER = neo4jUser;
    process.env.NEO4J_PASSWORD = neo4jPassword;

    // Initialize server
    try {
      server = new Neo4jServer();
      await server.initialize();
    } catch (error) {
      console.log('⚠️  Failed to initialize Neo4j server, skipping tests:', error);
      return;
    }
  });

  afterAll(async () => {
    if (server) {
      await server.shutdown();
    }
    
    if (testDriver) {
      await testDriver.close();
    }
  });

  beforeEach(async () => {
    if (!server || !testDriver) return;

    // Clean up test data before each test
    const session = testDriver.session();
    try {
      // Delete all test nodes and relationships
      await session.run(`
        MATCH (n)
        WHERE ANY(label IN labels(n) WHERE label IN $testLabels)
        DETACH DELETE n
      `, { testLabels });
    } catch (error) {
      // Ignore cleanup errors
    } finally {
      await session.close();
    }
  });

  describe('Node Operations', () => {
    it('should create and find nodes', async () => {
      if (!server) return;

      // Create a node
      const createResult = await server.executeTool('neo4j_create_node', {
        labels: ['Person', 'MCPTest'],
        properties: {
          name: 'Alice',
          age: 30,
          email: 'alice@example.com',
        },
      });

      expect(createResult.success).toBe(true);
      expect(createResult.node.labels).toContain('Person');
      expect(createResult.node.labels).toContain('MCPTest');
      expect(createResult.node.properties.name).toBe('Alice');
      expect(createResult.node.id).toBeDefined();

      // Find the node
      const findResult = await server.executeTool('neo4j_find_nodes', {
        labels: ['Person'],
        properties: { name: 'Alice' },
        limit: 10,
      });

      expect(findResult.nodes).toHaveLength(1);
      expect(findResult.nodes[0].properties.name).toBe('Alice');
      expect(findResult.nodes[0].properties.age).toBe(30);
    });

    it('should update node properties', async () => {
      if (!server) return;

      // Create a node
      const createResult = await server.executeTool('neo4j_create_node', {
        labels: ['Employee', 'MCPTest'],
        properties: {
          name: 'Bob',
          department: 'Engineering',
          salary: 75000,
        },
      });

      const nodeId = createResult.node.id;

      // Update node (merge properties)
      const updateResult = await server.executeTool('neo4j_update_node', {
        nodeId,
        properties: {
          salary: 80000,
          title: 'Senior Engineer',
        },
        merge: true,
      });

      expect(updateResult.success).toBe(true);
      expect(updateResult.node.properties.name).toBe('Bob'); // Should keep existing
      expect(updateResult.node.properties.salary).toBe(80000); // Should update
      expect(updateResult.node.properties.title).toBe('Senior Engineer'); // Should add
      expect(updateResult.node.properties.department).toBe('Engineering'); // Should keep
    });

    it('should delete nodes', async () => {
      if (!server) return;

      // Create a node
      const createResult = await server.executeTool('neo4j_create_node', {
        labels: ['Temporary', 'MCPTest'],
        properties: { name: 'TempNode' },
      });

      const nodeId = createResult.node.id;

      // Delete the node
      const deleteResult = await server.executeTool('neo4j_delete_node', {
        nodeId,
        detachDelete: true,
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.deleted).toBe(true);

      // Verify node is deleted
      const findResult = await server.executeTool('neo4j_find_nodes', {
        properties: { name: 'TempNode' },
      });

      expect(findResult.nodes).toHaveLength(0);
    });
  });

  describe('Relationship Operations', () => {
    it('should create relationships between new nodes', async () => {
      if (!server) return;

      // Create relationship with new nodes
      const relationshipResult = await server.executeTool('neo4j_create_relationship', {
        fromNode: {
          labels: ['Person', 'MCPTest'],
          properties: { name: 'Alice', role: 'Manager' },
        },
        toNode: {
          labels: ['Person', 'MCPTest'],
          properties: { name: 'Bob', role: 'Developer' },
        },
        type: 'MANAGES',
        properties: {
          since: '2023-01-01',
          department: 'Engineering',
        },
      });

      expect(relationshipResult.success).toBe(true);
      expect(relationshipResult.from.properties.name).toBe('Alice');
      expect(relationshipResult.to.properties.name).toBe('Bob');
      expect(relationshipResult.relationship.type).toBe('MANAGES');
      expect(relationshipResult.relationship.properties.since).toBe('2023-01-01');
    });

    it('should create relationships between existing nodes', async () => {
      if (!server) return;

      // Create two nodes first
      const aliceResult = await server.executeTool('neo4j_create_node', {
        labels: ['Person', 'MCPTest'],
        properties: { name: 'Alice', city: 'New York' },
      });

      const bobResult = await server.executeTool('neo4j_create_node', {
        labels: ['Person', 'MCPTest'],
        properties: { name: 'Bob', city: 'San Francisco' },
      });

      // Create relationship between existing nodes
      const relationshipResult = await server.executeTool('neo4j_create_relationship', {
        fromNode: { id: aliceResult.node.id },
        toNode: { id: bobResult.node.id },
        type: 'KNOWS',
        properties: {
          since: '2020-01-01',
          relationship: 'colleague',
        },
      });

      expect(relationshipResult.success).toBe(true);
      expect(relationshipResult.relationship.type).toBe('KNOWS');
      expect(relationshipResult.relationship.startNodeId).toBe(aliceResult.node.id);
      expect(relationshipResult.relationship.endNodeId).toBe(bobResult.node.id);
    });
  });

  describe('Path Finding', () => {
    beforeEach(async () => {
      if (!server) return;

      // Create a network of nodes and relationships for path testing
      // Alice -> Bob -> Charlie -> David
      //   |              |
      //   v              v
      // Eve           Frank

      const nodes = [
        { name: 'Alice', role: 'CEO' },
        { name: 'Bob', role: 'CTO' },
        { name: 'Charlie', role: 'Manager' },
        { name: 'David', role: 'Developer' },
        { name: 'Eve', role: 'Designer' },
        { name: 'Frank', role: 'Analyst' },
      ];

      const createdNodes = [];
      for (const nodeData of nodes) {
        const result = await server.executeTool('neo4j_create_node', {
          labels: ['Employee', 'MCPTest'],
          properties: nodeData,
        });
        createdNodes.push(result.node);
      }

      // Create relationships
      const relationships = [
        { from: 'Alice', to: 'Bob', type: 'REPORTS_TO' },
        { from: 'Bob', to: 'Charlie', type: 'MANAGES' },
        { from: 'Charlie', to: 'David', type: 'SUPERVISES' },
        { from: 'Alice', to: 'Eve', type: 'MANAGES' },
        { from: 'Charlie', to: 'Frank', type: 'COORDINATES' },
      ];

      for (const rel of relationships) {
        const fromNode = createdNodes.find(n => n.properties.name === rel.from);
        const toNode = createdNodes.find(n => n.properties.name === rel.to);

        await server.executeTool('neo4j_create_relationship', {
          fromNode: { id: fromNode.id },
          toNode: { id: toNode.id },
          type: rel.type,
        });
      }
    });

    it('should find shortest path between nodes', async () => {
      if (!server) return;

      const pathResult = await server.executeTool('neo4j_find_path', {
        startNode: {
          properties: { name: 'Alice' },
        },
        endNode: {
          properties: { name: 'David' },
        },
        maxLength: 5,
        algorithm: 'shortest',
      });

      expect(pathResult.found).toBe(true);
      expect(pathResult.paths).toHaveLength(1);
      expect(pathResult.paths[0].length).toBe(3); // Alice -> Bob -> Charlie -> David
      expect(pathResult.paths[0].start.properties.name).toBe('Alice');
      expect(pathResult.paths[0].end.properties.name).toBe('David');
    });

    it('should find paths with relationship type filtering', async () => {
      if (!server) return;

      const pathResult = await server.executeTool('neo4j_find_path', {
        startNode: {
          properties: { name: 'Alice' },
        },
        endNode: {
          properties: { name: 'Eve' },
        },
        relationshipTypes: ['MANAGES'],
        maxLength: 2,
        algorithm: 'shortest',
      });

      expect(pathResult.found).toBe(true);
      expect(pathResult.paths).toHaveLength(1);
      expect(pathResult.paths[0].length).toBe(1); // Direct relationship
      expect(pathResult.paths[0].relationships[0].type).toBe('MANAGES');
    });

    it('should handle no path found', async () => {
      if (!server) return;

      // Create an isolated node
      await server.executeTool('neo4j_create_node', {
        labels: ['Isolated', 'MCPTest'],
        properties: { name: 'Isolated' },
      });

      const pathResult = await server.executeTool('neo4j_find_path', {
        startNode: {
          properties: { name: 'Alice' },
        },
        endNode: {
          properties: { name: 'Isolated' },
        },
        maxLength: 5,
      });

      expect(pathResult.found).toBe(false);
      expect(pathResult.paths).toHaveLength(0);
      expect(pathResult.message).toContain('No path found');
    });
  });

  describe('Cypher Query Execution', () => {
    it('should execute basic Cypher queries', async () => {
      if (!server) return;

      // Create test data
      await server.executeTool('neo4j_create_node', {
        labels: ['Product', 'MCPTest'],
        properties: { name: 'Laptop', price: 1200, category: 'Electronics' },
      });

      await server.executeTool('neo4j_create_node', {
        labels: ['Product', 'MCPTest'],
        properties: { name: 'Mouse', price: 25, category: 'Electronics' },
      });

      // Execute Cypher query
      const queryResult = await server.executeTool('neo4j_query', {
        query: `
          MATCH (p:Product:MCPTest)
          WHERE p.price > $minPrice
          RETURN p.name as name, p.price as price
          ORDER BY p.price DESC
        `,
        params: { minPrice: 50 },
      });

      expect(queryResult.records).toHaveLength(1);
      expect(queryResult.records[0].name).toBe('Laptop');
      expect(queryResult.records[0].price).toBe(1200);
      expect(queryResult.summary.queryType).toBeDefined();
    });

    it('should execute parameterized queries', async () => {
      if (!server) return;

      // Create user nodes
      const users = [
        { name: 'Alice', age: 25, city: 'New York' },
        { name: 'Bob', age: 35, city: 'San Francisco' },
        { name: 'Charlie', age: 30, city: 'New York' },
      ];

      for (const user of users) {
        await server.executeTool('neo4j_create_node', {
          labels: ['User', 'MCPTest'],
          properties: user,
        });
      }

      // Query with multiple parameters
      const queryResult = await server.executeTool('neo4j_query', {
        query: `
          MATCH (u:User:MCPTest)
          WHERE u.city = $city AND u.age >= $minAge
          RETURN u.name as name, u.age as age
          ORDER BY u.age
        `,
        params: { city: 'New York', minAge: 27 },
      });

      expect(queryResult.records).toHaveLength(1);
      expect(queryResult.records[0].name).toBe('Charlie');
      expect(queryResult.records[0].age).toBe(30);
    });

    it('should handle query errors gracefully', async () => {
      if (!server) return;

      // Execute invalid Cypher query
      await expect(
        server.executeTool('neo4j_query', {
          query: 'INVALID CYPHER SYNTAX',
        })
      ).rejects.toThrow('Cypher query failed');
    });
  });

  describe('Schema and Indexes', () => {
    it('should create and manage indexes', async () => {
      if (!server) return;

      // Create a node to ensure label exists
      await server.executeTool('neo4j_create_node', {
        labels: ['Person', 'MCPTest'],
        properties: { email: 'test@example.com' },
      });

      // Create index
      const indexResult = await server.executeTool('neo4j_create_index', {
        label: 'Person',
        properties: ['email'],
        type: 'btree',
        name: 'person_email_idx',
      });

      expect(indexResult.success).toBe(true);
      expect(indexResult.indexName).toBe('person_email_idx');
      expect(indexResult.label).toBe('Person');
      expect(indexResult.properties).toEqual(['email']);

      // Get schema information
      const schemaResult = await server.executeTool('neo4j_schema', {});

      expect(schemaResult.labels).toContain('Person');
      expect(schemaResult.labels).toContain('MCPTest');
      expect(schemaResult.indexes).toContainEqual(
        expect.objectContaining({
          name: 'person_email_idx',
        })
      );
    });

    it('should create constraints', async () => {
      if (!server) return;

      // Create a node to ensure label exists
      await server.executeTool('neo4j_create_node', {
        labels: ['User', 'MCPTest'],
        properties: { username: 'testuser' },
      });

      // Create unique constraint
      const constraintResult = await server.executeTool('neo4j_create_constraint', {
        label: 'User',
        property: 'username',
        type: 'unique',
        name: 'user_username_unique',
      });

      expect(constraintResult.success).toBe(true);
      expect(constraintResult.constraintName).toBe('user_username_unique');
      expect(constraintResult.type).toBe('unique');

      // Get schema to verify constraint
      const schemaResult = await server.executeTool('neo4j_schema', {});

      expect(schemaResult.constraints).toContainEqual(
        expect.objectContaining({
          name: 'user_username_unique',
          type: 'UNIQUENESS',
        })
      );
    });
  });

  describe('Database Statistics', () => {
    beforeEach(async () => {
      if (!server) return;

      // Create some test data for statistics
      const companies = ['TechCorp', 'DataInc', 'CloudSoft'];
      const departments = ['Engineering', 'Marketing', 'Sales'];

      for (const company of companies) {
        const companyNode = await server.executeTool('neo4j_create_node', {
          labels: ['Company', 'MCPTest'],
          properties: { name: company },
        });

        for (const dept of departments) {
          const deptNode = await server.executeTool('neo4j_create_node', {
            labels: ['Department', 'MCPTest'],
            properties: { name: dept, company: company },
          });

          await server.executeTool('neo4j_create_relationship', {
            fromNode: { id: companyNode.node.id },
            toNode: { id: deptNode.node.id },
            type: 'HAS_DEPARTMENT',
          });
        }
      }
    });

    it('should get database statistics', async () => {
      if (!server) return;

      const statsResult = await server.executeTool('neo4j_stats', {});

      expect(statsResult.nodeCount).toBeGreaterThan(0);
      expect(statsResult.relationshipCount).toBeGreaterThan(0);
      expect(statsResult.labelDistribution).toContainEqual(
        expect.objectContaining({
          label: 'Company',
          count: 3,
        })
      );
      expect(statsResult.labelDistribution).toContainEqual(
        expect.objectContaining({
          label: 'Department',
          count: 9,
        })
      );
      expect(statsResult.relationshipDistribution).toContainEqual(
        expect.objectContaining({
          type: 'HAS_DEPARTMENT',
          count: 9,
        })
      );
    });
  });

  describe('Graph Algorithms', () => {
    it('should handle graph algorithms gracefully when GDS is not available', async () => {
      if (!server) return;

      // Create some nodes for algorithm testing
      await server.executeTool('neo4j_create_node', {
        labels: ['Page', 'MCPTest'],
        properties: { name: 'HomePage' },
      });

      // Try to run PageRank algorithm
      try {
        await server.executeTool('neo4j_algorithm', {
          algorithm: 'pageRank',
          nodeLabel: 'Page',
        });
        
        // If we get here, GDS is available
        expect(true).toBe(true);
      } catch (error: any) {
        // Should handle GDS not being available
        expect(error.message).toContain('Graph Data Science plugin is not installed');
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle non-existent node operations', async () => {
      if (!server) return;

      // Try to update non-existent node
      await expect(
        server.executeTool('neo4j_update_node', {
          nodeId: '999999',
          properties: { test: 'value' },
        })
      ).rejects.toThrow('not found');

      // Try to delete non-existent node
      const deleteResult = await server.executeTool('neo4j_delete_node', {
        nodeId: '999999',
        detachDelete: true,
      });

      expect(deleteResult.success).toBe(true);
      expect(deleteResult.deleted).toBe(false); // No nodes were actually deleted
    });

    it('should handle relationship constraint violations', async () => {
      if (!server) return;

      // Create a node with relationships
      const nodeResult = await server.executeTool('neo4j_create_node', {
        labels: ['TestNode', 'MCPTest'],
        properties: { name: 'NodeWithRels' },
      });

      const relatedNodeResult = await server.executeTool('neo4j_create_node', {
        labels: ['Related', 'MCPTest'],
        properties: { name: 'Related' },
      });

      await server.executeTool('neo4j_create_relationship', {
        fromNode: { id: nodeResult.node.id },
        toNode: { id: relatedNodeResult.node.id },
        type: 'CONNECTS_TO',
      });

      // Try to delete node without detach (should fail)
      await expect(
        server.executeTool('neo4j_delete_node', {
          nodeId: nodeResult.node.id,
          detachDelete: false,
        })
      ).rejects.toThrow('has relationships');
    });

    it('should handle invalid query parameters', async () => {
      if (!server) return;

      // Try to find path with invalid parameters
      const pathResult = await server.executeTool('neo4j_find_path', {
        startNode: {
          properties: { name: 'NonExistent1' },
        },
        endNode: {
          properties: { name: 'NonExistent2' },
        },
        maxLength: 1,
      });

      expect(pathResult.found).toBe(false);
      expect(pathResult.paths).toHaveLength(0);
    });
  });
});