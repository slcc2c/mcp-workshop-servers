/**
 * Neo4j MCP Server
 * Provides graph database operations with Cypher query support
 */

import { z } from 'zod';
import neo4j, { Driver, Session, Node, Relationship } from 'neo4j-driver';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const CypherQuerySchema = z.object({
  query: z.string().describe('Cypher query to execute'),
  params: z.record(z.any()).optional().describe('Query parameters'),
  database: z.string().optional().describe('Database name (uses default if not specified)'),
});

const CreateNodeSchema = z.object({
  labels: z.array(z.string()).min(1).describe('Node labels'),
  properties: z.record(z.any()).optional().describe('Node properties'),
  database: z.string().optional().describe('Database name'),
});

const CreateRelationshipSchema = z.object({
  fromNode: z.object({
    labels: z.array(z.string()).optional(),
    properties: z.record(z.any()).optional(),
    id: z.string().optional().describe('Node ID if referring to existing node'),
  }).describe('Source node'),
  toNode: z.object({
    labels: z.array(z.string()).optional(),
    properties: z.record(z.any()).optional(),
    id: z.string().optional().describe('Node ID if referring to existing node'),
  }).describe('Target node'),
  type: z.string().describe('Relationship type'),
  properties: z.record(z.any()).optional().describe('Relationship properties'),
  database: z.string().optional().describe('Database name'),
});

const FindNodesSchema = z.object({
  labels: z.array(z.string()).optional().describe('Filter by labels'),
  properties: z.record(z.any()).optional().describe('Filter by properties'),
  limit: z.number().default(100).describe('Maximum nodes to return'),
  database: z.string().optional().describe('Database name'),
});

const FindPathSchema = z.object({
  startNode: z.object({
    labels: z.array(z.string()).optional(),
    properties: z.record(z.any()).optional(),
  }).describe('Starting node'),
  endNode: z.object({
    labels: z.array(z.string()).optional(),
    properties: z.record(z.any()).optional(),
  }).describe('Ending node'),
  relationshipTypes: z.array(z.string()).optional().describe('Allowed relationship types'),
  maxLength: z.number().default(5).describe('Maximum path length'),
  algorithm: z.enum(['shortest', 'all']).default('shortest').describe('Path finding algorithm'),
  database: z.string().optional().describe('Database name'),
});

const UpdateNodeSchema = z.object({
  nodeId: z.string().describe('Node ID'),
  properties: z.record(z.any()).describe('Properties to update'),
  merge: z.boolean().default(true).describe('Merge with existing properties'),
  database: z.string().optional().describe('Database name'),
});

const DeleteNodeSchema = z.object({
  nodeId: z.string().describe('Node ID'),
  detachDelete: z.boolean().default(true).describe('Delete relationships too'),
  database: z.string().optional().describe('Database name'),
});

const CreateIndexSchema = z.object({
  label: z.string().describe('Node label'),
  properties: z.array(z.string()).min(1).describe('Properties to index'),
  type: z.enum(['btree', 'fulltext', 'point', 'range']).default('btree').describe('Index type'),
  name: z.string().optional().describe('Index name'),
  database: z.string().optional().describe('Database name'),
});

const CreateConstraintSchema = z.object({
  label: z.string().describe('Node label'),
  property: z.string().describe('Property name'),
  type: z.enum(['unique', 'exists', 'key']).describe('Constraint type'),
  name: z.string().optional().describe('Constraint name'),
  database: z.string().optional().describe('Database name'),
});

export class Neo4jServer extends BaseMCPServer {
  private driver!: Driver;
  private defaultDatabase?: string;
  private connectionString?: string;

  constructor() {
    super('neo4j', '1.0.0', 'Neo4j graph database operations with Cypher support');
  }

  protected async onInitialize(): Promise<void> {
    // Get connection string from environment or 1Password
    this.connectionString = process.env.NEO4J_URL || process.env.NEO4J_URI;
    
    if (!this.connectionString) {
      throw new Error('Neo4j connection string not found. Set NEO4J_URL or NEO4J_URI environment variable.');
    }

    // Extract credentials from connection string or use separate env vars
    const username = process.env.NEO4J_USER || 'neo4j';
    const password = process.env.NEO4J_PASSWORD;
    
    if (!password) {
      throw new Error('Neo4j password not found. Set NEO4J_PASSWORD environment variable.');
    }

    // Extract default database from env
    this.defaultDatabase = process.env.NEO4J_DATABASE || 'neo4j';

    // Create driver
    this.driver = neo4j.driver(
      this.connectionString,
      neo4j.auth.basic(username, password),
      {
        maxConnectionPoolSize: 10,
        connectionAcquisitionTimeout: 60000,
        logging: {
          level: 'info',
          logger: (_level: string, message: string) => this.logger.info(message),
        },
      }
    );

    // Test connection
    const session = this.driver.session();
    try {
      await session.run('RETURN 1');
      this.logger.info('Neo4j server initialized', {
        defaultDatabase: this.defaultDatabase,
      });
    } catch (error) {
      throw new Error(`Failed to connect to Neo4j: ${error}`);
    } finally {
      await session.close();
    }
  }

  protected async onShutdown(): Promise<void> {
    await this.driver.close();
    this.logger.info('Neo4j connection closed');
  }

  private getSession(database?: string): Session {
    return this.driver.session({
      database: database || this.defaultDatabase,
      defaultAccessMode: neo4j.session.WRITE,
    });
  }

  private formatNode(node: Node): any {
    return {
      id: node.identity.toString(),
      labels: node.labels,
      properties: node.properties,
    };
  }

  private formatRelationship(rel: Relationship): any {
    return {
      id: rel.identity.toString(),
      type: rel.type,
      startNodeId: rel.start.toString(),
      endNodeId: rel.end.toString(),
      properties: rel.properties,
    };
  }

  private formatResult(record: any): any {
    const result: any = {};
    
    record.keys.forEach((key: string) => {
      const value = record.get(key);
      
      if (neo4j.isNode(value)) {
        result[key] = this.formatNode(value);
      } else if (neo4j.isRelationship(value)) {
        result[key] = this.formatRelationship(value);
      } else if (neo4j.isPath(value)) {
        result[key] = {
          start: this.formatNode(value.start),
          end: this.formatNode(value.end),
          length: value.length,
          nodes: (value as any).nodes.map((n: Node) => this.formatNode(n)),
          relationships: (value as any).relationships.map((r: Relationship) => this.formatRelationship(r)),
        };
      } else if (neo4j.integer.inSafeRange(value)) {
        result[key] = neo4j.integer.toNumber(value);
      } else {
        result[key] = value;
      }
    });
    
    return result;
  }

  protected async registerTools(): Promise<void> {
    // Cypher query execution
    this.registerTool(
      'neo4j_query',
      'Execute a Cypher query',
      CypherQuerySchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const result = await session.run(params.query, params.params || {});
          
          return {
            records: result.records.map(record => this.formatResult(record)),
            summary: {
              query: params.query,
              queryType: result.summary.query.text,
              counters: result.summary.counters,
              executionTime: result.summary.resultAvailableAfter?.toNumber(),
            },
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Cypher query failed: ${error.message}`);
        } finally {
          await session.close();
        }
      })
    );

    // Create node
    this.registerTool(
      'neo4j_create_node',
      'Create a new node',
      CreateNodeSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const labels = params.labels.join(':');
          const query = `CREATE (n:${labels} $props) RETURN n`;
          
          const result = await session.run(query, {
            props: params.properties || {},
          });
          
          const node = result.records[0].get('n');
          
          return {
            success: true,
            node: this.formatNode(node),
          };
        } finally {
          await session.close();
        }
      })
    );

    // Create relationship
    this.registerTool(
      'neo4j_create_relationship',
      'Create a relationship between nodes',
      CreateRelationshipSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          let query: string;
          const queryParams: any = {
            relProps: params.properties || {},
          };

          // Build query based on whether nodes exist or need to be created
          if (params.fromNode.id && params.toNode.id) {
            // Both nodes exist
            query = `
              MATCH (from), (to)
              WHERE ID(from) = $fromId AND ID(to) = $toId
              CREATE (from)-[r:${params.type} $relProps]->(to)
              RETURN from, r, to
            `;
            queryParams.fromId = neo4j.int(params.fromNode.id);
            queryParams.toId = neo4j.int(params.toNode.id);
          } else {
            // Create nodes if needed
            const fromLabels = params.fromNode.labels?.join(':') || 'Node';
            const toLabels = params.toNode.labels?.join(':') || 'Node';
            
            query = `
              CREATE (from:${fromLabels} $fromProps)
              CREATE (to:${toLabels} $toProps)
              CREATE (from)-[r:${params.type} $relProps]->(to)
              RETURN from, r, to
            `;
            queryParams.fromProps = params.fromNode.properties || {};
            queryParams.toProps = params.toNode.properties || {};
          }

          const result = await session.run(query, queryParams);
          
          if (result.records.length === 0) {
            throw new ResourceNotFoundError('Nodes not found');
          }

          const record = result.records[0];
          
          return {
            success: true,
            from: this.formatNode(record.get('from')),
            relationship: this.formatRelationship(record.get('r')),
            to: this.formatNode(record.get('to')),
          };
        } finally {
          await session.close();
        }
      })
    );

    // Find nodes
    this.registerTool(
      'neo4j_find_nodes',
      'Find nodes by labels and properties',
      FindNodesSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          let whereClause = '';
          const queryParams: any = {};

          if (params.labels && params.labels.length > 0) {
            whereClause = `(${params.labels.map((l: string) => `n:${l}`).join(' OR ')})`;
          }

          if (params.properties && Object.keys(params.properties).length > 0) {
            const propConditions = Object.entries(params.properties).map(([key, value], index) => {
              queryParams[`prop${index}`] = value;
              return `n.${key} = $prop${index}`;
            }).join(' AND ');
            
            whereClause = whereClause 
              ? `${whereClause} AND ${propConditions}`
              : propConditions;
          }

          const query = whereClause
            ? `MATCH (n) WHERE ${whereClause} RETURN n LIMIT $limit`
            : `MATCH (n) RETURN n LIMIT $limit`;

          queryParams.limit = neo4j.int(params.limit);

          const result = await session.run(query, queryParams);
          
          return {
            nodes: result.records.map(record => this.formatNode(record.get('n'))),
            count: result.records.length,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Find shortest path
    this.registerTool(
      'neo4j_find_path',
      'Find path between nodes',
      FindPathSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          // Build match clauses for start and end nodes
          const buildNodeMatch = (node: any, varName: string): [string, any] => {
            const conditions: string[] = [];
            const props: any = {};

            if (node.labels && node.labels.length > 0) {
              conditions.push(`(${node.labels.map((l: string) => `${varName}:${l}`).join(' OR ')})`);
            }

            if (node.properties) {
              Object.entries(node.properties).forEach(([key, value], index) => {
                props[`${varName}Prop${index}`] = value;
                conditions.push(`${varName}.${key} = $${varName}Prop${index}`);
              });
            }

            return [conditions.join(' AND '), props];
          };

          const [startConditions, startProps] = buildNodeMatch(params.startNode, 'start');
          const [endConditions, endProps] = buildNodeMatch(params.endNode, 'end');

          const relPattern = params.relationshipTypes && params.relationshipTypes.length > 0
            ? `:${params.relationshipTypes.join('|')}`
            : '';

          const pathFunction = params.algorithm === 'shortest' 
            ? 'shortestPath' 
            : 'allShortestPaths';

          const query = `
            MATCH (start), (end)
            WHERE ${startConditions || 'true'} AND ${endConditions || 'true'}
            MATCH p = ${pathFunction}((start)-[${relPattern}*..${params.maxLength}]-(end))
            RETURN p
            ${params.algorithm === 'all' ? '' : 'LIMIT 1'}
          `;

          const result = await session.run(query, {
            ...startProps,
            ...endProps,
          });

          if (result.records.length === 0) {
            return {
              paths: [],
              found: false,
              message: 'No path found between the specified nodes',
            };
          }

          const paths = result.records.map(record => {
            const path = record.get('p');
            return {
              start: this.formatNode(path.start),
              end: this.formatNode(path.end),
              length: path.length,
              nodes: path.nodes.map((n: Node) => this.formatNode(n)),
              relationships: path.relationships.map((r: Relationship) => this.formatRelationship(r)),
            };
          });

          return {
            paths,
            found: true,
            count: paths.length,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Update node
    this.registerTool(
      'neo4j_update_node',
      'Update node properties',
      UpdateNodeSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const query = params.merge
            ? `MATCH (n) WHERE ID(n) = $nodeId SET n += $props RETURN n`
            : `MATCH (n) WHERE ID(n) = $nodeId SET n = $props RETURN n`;

          const result = await session.run(query, {
            nodeId: neo4j.int(params.nodeId),
            props: params.properties,
          });

          if (result.records.length === 0) {
            throw new ResourceNotFoundError(`Node with ID ${params.nodeId} not found`);
          }

          const node = result.records[0].get('n');
          
          return {
            success: true,
            node: this.formatNode(node),
          };
        } finally {
          await session.close();
        }
      })
    );

    // Delete node
    this.registerTool(
      'neo4j_delete_node',
      'Delete a node',
      DeleteNodeSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const query = params.detachDelete
            ? `MATCH (n) WHERE ID(n) = $nodeId DETACH DELETE n`
            : `MATCH (n) WHERE ID(n) = $nodeId DELETE n`;

          const result = await session.run(query, {
            nodeId: neo4j.int(params.nodeId),
          });

          return {
            success: true,
            deleted: result.summary.counters.updates().nodesDeleted > 0,
            relationshipsDeleted: result.summary.counters.updates().relationshipsDeleted,
          };
        } catch (error: any) {
          if (error.message.includes('still has relationships')) {
            throw new InvalidParamsError('Node has relationships. Use detachDelete=true to delete node and its relationships.');
          }
          throw error;
        } finally {
          await session.close();
        }
      })
    );

    // Create index
    this.registerTool(
      'neo4j_create_index',
      'Create an index',
      CreateIndexSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const indexName = params.name || `idx_${params.label}_${params.properties.join('_')}`;
          const properties = params.properties.map((p: string) => `n.${p}`).join(', ');
          
          let query: string;
          switch (params.type) {
            case 'fulltext':
              query = `CREATE FULLTEXT INDEX ${indexName} FOR (n:${params.label}) ON EACH [${properties}]`;
              break;
            case 'point':
              query = `CREATE POINT INDEX ${indexName} FOR (n:${params.label}) ON (${properties})`;
              break;
            case 'range':
              query = `CREATE RANGE INDEX ${indexName} FOR (n:${params.label}) ON (${properties})`;
              break;
            default:
              query = `CREATE INDEX ${indexName} FOR (n:${params.label}) ON (${properties})`;
          }

          await session.run(query);
          
          return {
            success: true,
            indexName,
            label: params.label,
            properties: params.properties,
            type: params.type,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Create constraint
    this.registerTool(
      'neo4j_create_constraint',
      'Create a constraint',
      CreateConstraintSchema,
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const constraintName = params.name || `${params.type}_${params.label}_${params.property}`;
          
          let query: string;
          switch (params.type) {
            case 'unique':
              query = `CREATE CONSTRAINT ${constraintName} FOR (n:${params.label}) REQUIRE n.${params.property} IS UNIQUE`;
              break;
            case 'exists':
              query = `CREATE CONSTRAINT ${constraintName} FOR (n:${params.label}) REQUIRE n.${params.property} IS NOT NULL`;
              break;
            case 'key':
              query = `CREATE CONSTRAINT ${constraintName} FOR (n:${params.label}) REQUIRE n.${params.property} IS NODE KEY`;
              break;
            default:
              throw new Error(`Unsupported constraint type: ${params.type}`);
          }

          await session.run(query);
          
          return {
            success: true,
            constraintName,
            label: params.label,
            property: params.property,
            type: params.type,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Schema information
    this.registerTool(
      'neo4j_schema',
      'Get database schema information',
      z.object({
        database: z.string().optional().describe('Database name'),
      }),
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          // Get labels
          const labelsResult = await session.run('CALL db.labels()');
          const labels = labelsResult.records.map(r => r.get('label'));

          // Get relationship types
          const relTypesResult = await session.run('CALL db.relationshipTypes()');
          const relationshipTypes = relTypesResult.records.map(r => r.get('relationshipType'));

          // Get constraints
          const constraintsResult = await session.run('SHOW CONSTRAINTS');
          const constraints = constraintsResult.records.map(r => ({
            name: r.get('name'),
            type: r.get('type'),
            entityType: r.get('entityType'),
            labelsOrTypes: r.get('labelsOrTypes'),
            properties: r.get('properties'),
          }));

          // Get indexes
          const indexesResult = await session.run('SHOW INDEXES');
          const indexes = indexesResult.records.map(r => ({
            name: r.get('name'),
            type: r.get('type'),
            entityType: r.get('entityType'),
            labelsOrTypes: r.get('labelsOrTypes'),
            properties: r.get('properties'),
            state: r.get('state'),
          }));

          return {
            labels,
            relationshipTypes,
            constraints,
            indexes,
            database: params.database || this.defaultDatabase,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Database statistics
    this.registerTool(
      'neo4j_stats',
      'Get database statistics',
      z.object({
        database: z.string().optional().describe('Database name'),
      }),
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          // Get node count
          const nodeCountResult = await session.run('MATCH (n) RETURN count(n) as count');
          const nodeCount = neo4j.integer.toNumber(nodeCountResult.records[0].get('count'));

          // Get relationship count
          const relCountResult = await session.run('MATCH ()-[r]->() RETURN count(r) as count');
          const relationshipCount = neo4j.integer.toNumber(relCountResult.records[0].get('count'));

          // Get label distribution
          const labelStatsResult = await session.run(`
            MATCH (n)
            UNWIND labels(n) as label
            RETURN label, count(*) as count
            ORDER BY count DESC
          `);
          const labelDistribution = labelStatsResult.records.map(r => ({
            label: r.get('label'),
            count: neo4j.integer.toNumber(r.get('count')),
          }));

          // Get relationship type distribution
          const relTypeStatsResult = await session.run(`
            MATCH ()-[r]->()
            RETURN type(r) as type, count(*) as count
            ORDER BY count DESC
          `);
          const relationshipDistribution = relTypeStatsResult.records.map(r => ({
            type: r.get('type'),
            count: neo4j.integer.toNumber(r.get('count')),
          }));

          return {
            database: params.database || this.defaultDatabase,
            nodeCount,
            relationshipCount,
            labelDistribution,
            relationshipDistribution,
          };
        } finally {
          await session.close();
        }
      })
    );

    // Run graph algorithms
    this.registerTool(
      'neo4j_algorithm',
      'Run graph algorithms (requires GDS plugin)',
      z.object({
        algorithm: z.enum(['pageRank', 'communityDetection', 'shortestPath', 'centrality']).describe('Algorithm to run'),
        nodeLabel: z.string().optional().describe('Node label to filter'),
        relationshipType: z.string().optional().describe('Relationship type to filter'),
        database: z.string().optional().describe('Database name'),
      }),
      createToolHandler<any>(async (params) => {
        const session = this.getSession(params.database);
        
        try {
          const graphName = `graph_${Date.now()}`;

          // Create graph projection
          const nodeProjection = params.nodeLabel || '*';
          const relProjection = params.relationshipType || '*';
          
          await session.run(`
            CALL gds.graph.project(
              $graphName,
              $nodeProjection,
              $relProjection
            )
          `, {
            graphName,
            nodeProjection,
            relProjection,
          });

          try {
            let result: any;
            let query: string;
            
            switch (params.algorithm) {
              case 'pagerank':
                query = `
                  CALL gds.pageRank.${params.writeProperty ? 'write' : 'stream'}($graphName, {
                    writeProperty: $writeProperty
                  })
                  YIELD nodeId, score
                  RETURN gds.util.asNode(nodeId) AS node, score
                  ORDER BY score DESC
                  LIMIT 10
                `;
                break;
                
              case 'communityDetection':
                query = `
                  CALL gds.louvain.${params.writeProperty ? 'write' : 'stream'}($graphName, {
                    writeProperty: $writeProperty
                  })
                  YIELD nodeId, communityId
                  RETURN communityId, collect(gds.util.asNode(nodeId)) AS nodes
                  ORDER BY size(nodes) DESC
                  LIMIT 10
                `;
                break;
                
              case 'centrality':
                query = `
                  CALL gds.betweenness.${params.writeProperty ? 'write' : 'stream'}($graphName, {
                    writeProperty: $writeProperty
                  })
                  YIELD nodeId, score
                  RETURN gds.util.asNode(nodeId) AS node, score
                  ORDER BY score DESC
                  LIMIT 10
                `;
                break;
                
              case 'similarity':
                query = `
                  CALL gds.nodeSimilarity.${params.writeProperty ? 'write' : 'stream'}($graphName, {
                    writeRelationshipType: 'SIMILAR',
                    writeProperty: $writeProperty
                  })
                  YIELD node1, node2, similarity
                  RETURN gds.util.asNode(node1) AS node1, gds.util.asNode(node2) AS node2, similarity
                  ORDER BY similarity DESC
                  LIMIT 10
                `;
                break;
              default:
                throw new Error(`Unsupported algorithm: ${params.algorithm}`);
            }

            result = await session.run(query, {
              graphName,
              writeProperty: params.writeProperty,
            });

            // Drop the graph projection
            await session.run('CALL gds.graph.drop($graphName)', { graphName });

            return {
              algorithm: params.algorithm,
              results: result.records.map((record: any) => this.formatResult(record)),
              writeProperty: params.writeProperty,
            };
          } finally {
            // Ensure graph is dropped even if algorithm fails
            try {
              await session.run('CALL gds.graph.drop($graphName, false)', { graphName });
            } catch (e) {
              // Ignore error if graph was already dropped
            }
          }
        } catch (error: any) {
          if (error.message.includes('no procedure with the name')) {
            throw new InvalidParamsError('Graph Data Science plugin is not installed. Please install GDS to use graph algorithms.');
          }
          throw error;
        } finally {
          await session.close();
        }
      })
    );
  }
}