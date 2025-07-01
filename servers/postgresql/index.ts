/**
 * PostgreSQL MCP Server
 * Provides database operations with connection pooling and transaction support
 * 
 * Supports MongoDB-style query operators for flexible filtering:
 * - $gte: Greater than or equal to
 * - $gt: Greater than
 * - $lte: Less than or equal to
 * - $lt: Less than
 * - $ne: Not equal to
 * - $in: Value is in array
 * - $nin: Value is not in array
 * 
 * Example usage:
 * where: { age: { $gte: 18 }, status: { $in: ['active', 'pending'] } }
 */

import { z } from 'zod';
import { Pool, PoolConfig } from 'pg';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const QuerySchema = z.object({
  query: z.string().describe('SQL query to execute'),
  params: z.array(z.any()).optional().describe('Query parameters for prepared statements'),
  database: z.string().optional().describe('Database name (uses default if not specified)'),
});

const TransactionSchema = z.object({
  queries: z.array(z.object({
    query: z.string(),
    params: z.array(z.any()).optional(),
  })).describe('Array of queries to execute in a transaction'),
  database: z.string().optional().describe('Database name (uses default if not specified)'),
});

const TableSchema = z.object({
  database: z.string().optional().describe('Database name to list tables from'),
  schema: z.string().default('public').describe('Schema name'),
});

const TableInfoSchema = z.object({
  table: z.string().describe('Table name'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

const CreateTableSchema = z.object({
  table: z.string().describe('Table name'),
  columns: z.array(z.object({
    name: z.string(),
    type: z.string(),
    nullable: z.boolean().default(true),
    primaryKey: z.boolean().default(false),
    unique: z.boolean().default(false),
    default: z.string().optional(),
  })).describe('Column definitions'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

const InsertSchema = z.object({
  table: z.string().describe('Table name'),
  data: z.record(z.any()).describe('Data to insert (column: value pairs)'),
  returning: z.array(z.string()).optional().describe('Columns to return'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

const UpdateSchema = z.object({
  table: z.string().describe('Table name'),
  data: z.record(z.any()).describe('Data to update (column: value pairs)'),
  where: z.record(z.any()).describe('WHERE conditions'),
  returning: z.array(z.string()).optional().describe('Columns to return'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

const DeleteSchema = z.object({
  table: z.string().describe('Table name'),
  where: z.record(z.any()).describe('WHERE conditions'),
  returning: z.array(z.string()).optional().describe('Columns to return'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

const SelectSchema = z.object({
  table: z.string().describe('Table name'),
  columns: z.array(z.string()).default(['*']).describe('Columns to select'),
  where: z.record(z.any()).optional().describe('WHERE conditions'),
  orderBy: z.array(z.object({
    column: z.string(),
    direction: z.enum(['ASC', 'DESC']).default('ASC'),
  })).optional().describe('ORDER BY clauses'),
  limit: z.number().optional().describe('LIMIT value'),
  offset: z.number().optional().describe('OFFSET value'),
  database: z.string().optional().describe('Database name'),
  schema: z.string().default('public').describe('Schema name'),
});

export class PostgreSQLServer extends BaseMCPServer {
  private pools: Map<string, Pool> = new Map();
  private defaultDatabase?: string;
  private connectionString?: string;

  constructor() {
    super('postgresql', '1.0.0', 'PostgreSQL database operations with connection pooling');
  }

  protected async onInitialize(): Promise<void> {
    // Get connection string from environment or 1Password
    this.connectionString = process.env.POSTGRES_URL || process.env.DATABASE_URL;
    
    if (!this.connectionString) {
      throw new Error('PostgreSQL connection string not found. Set POSTGRES_URL or DATABASE_URL environment variable.');
    }

    // Extract default database from connection string
    const match = this.connectionString.match(/\/([^/?]+)(\?|$)/);
    this.defaultDatabase = match ? match[1] : 'postgres';

    // Create initial connection pool
    await this.getPool();
    
    this.logger.info('PostgreSQL server initialized', {
      defaultDatabase: this.defaultDatabase,
    });
  }

  protected async onShutdown(): Promise<void> {
    // Close all connection pools
    for (const [name, pool] of this.pools) {
      await pool.end();
      this.logger.info('Closed connection pool', { database: name });
    }
    this.pools.clear();
  }

  private async getPool(database?: string): Promise<Pool> {
    const dbName = database || this.defaultDatabase || 'postgres';
    
    if (!this.pools.has(dbName)) {
      const poolConfig: PoolConfig = {
        connectionString: this.connectionString,
        database: dbName,
        max: 20, // Maximum number of clients in the pool
        idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
        connectionTimeoutMillis: 2000, // Return an error after 2 seconds if connection could not be established
      };

      const pool = new Pool(poolConfig);
      
      // Test the connection
      try {
        await pool.query('SELECT 1');
      } catch (error) {
        await pool.end();
        throw new Error(`Failed to connect to database "${dbName}": ${error}`);
      }

      this.pools.set(dbName, pool);
      this.logger.info('Created connection pool', { database: dbName });
    }

    return this.pools.get(dbName)!;
  }

  protected async registerTools(): Promise<void> {
    // Query execution
    this.registerTool(
      'postgres_query',
      'Execute a SQL query',
      QuerySchema,
      createToolHandler<z.infer<typeof QuerySchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        try {
          const result = await pool.query(params.query, params.params);
          
          return {
            rows: result.rows,
            rowCount: result.rowCount,
            fields: result.fields?.map(f => ({
              name: f.name,
              dataTypeID: f.dataTypeID,
            })),
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Query failed: ${error.message}`);
        }
      })
    );

    // Transaction execution
    this.registerTool(
      'postgres_transaction',
      'Execute multiple queries in a transaction',
      TransactionSchema,
      createToolHandler<z.infer<typeof TransactionSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        const client = await pool.connect();
        
        try {
          await client.query('BEGIN');
          
          const results = [];
          for (const query of params.queries) {
            const result = await client.query(query.query, query.params);
            results.push({
              rowCount: result.rowCount,
              rows: result.rows,
            });
          }
          
          await client.query('COMMIT');
          
          return {
            success: true,
            results,
            totalQueries: params.queries.length,
          };
        } catch (error: any) {
          await client.query('ROLLBACK');
          throw new InvalidParamsError(`Transaction failed: ${error.message}`);
        } finally {
          client.release();
        }
      })
    );

    // List tables
    this.registerTool(
      'postgres_list_tables',
      'List all tables in a database',
      TableSchema,
      createToolHandler<z.infer<typeof TableSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const query = `
          SELECT 
            schemaname AS schema,
            tablename AS name,
            tableowner AS owner
          FROM pg_tables
          WHERE schemaname = $1
          ORDER BY tablename;
        `;
        
        const result = await pool.query(query, [params.schema]);
        
        return {
          tables: result.rows,
          count: result.rowCount,
        };
      })
    );

    // Get table information
    this.registerTool(
      'postgres_table_info',
      'Get information about a table including columns',
      TableInfoSchema,
      createToolHandler<z.infer<typeof TableInfoSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const query = `
          SELECT 
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default,
            ordinal_position
          FROM information_schema.columns
          WHERE table_schema = $1 AND table_name = $2
          ORDER BY ordinal_position;
        `;
        
        const result = await pool.query(query, [params.schema, params.table]);
        
        if (result.rowCount === 0) {
          throw new ResourceNotFoundError(`Table "${params.schema}.${params.table}" not found`);
        }
        
        return {
          table: params.table,
          schema: params.schema,
          columns: result.rows.map(row => ({
            name: row.column_name,
            type: row.data_type,
            maxLength: row.character_maximum_length,
            nullable: row.is_nullable === 'YES',
            default: row.column_default,
            position: row.ordinal_position,
          })),
        };
      })
    );

    // Create table
    this.registerTool(
      'postgres_create_table',
      'Create a new table',
      CreateTableSchema,
      createToolHandler<z.infer<typeof CreateTableSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const columns = params.columns.map(col => {
          let def = `"${col.name}" ${col.type}`;
          if (!col.nullable) def += ' NOT NULL';
          if (col.primaryKey) def += ' PRIMARY KEY';
          if (col.unique) def += ' UNIQUE';
          if (col.default !== undefined) def += ` DEFAULT ${col.default}`;
          return def;
        }).join(', ');
        
        const query = `CREATE TABLE "${params.schema}"."${params.table}" (${columns});`;
        
        try {
          await pool.query(query);
          return {
            success: true,
            table: params.table,
            schema: params.schema,
            message: `Table "${params.schema}.${params.table}" created successfully`,
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Failed to create table: ${error.message}`);
        }
      })
    );

    // Insert data
    this.registerTool(
      'postgres_insert',
      'Insert data into a table',
      InsertSchema,
      createToolHandler<z.infer<typeof InsertSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const columns = Object.keys(params.data);
        const values = Object.values(params.data);
        const placeholders = values.map((_, i) => `$${i + 1}`).join(', ');
        
        let query = `INSERT INTO "${params.schema}"."${params.table}" (${columns.map(c => `"${c}"`).join(', ')}) VALUES (${placeholders})`;
        
        if (params.returning && params.returning.length > 0) {
          query += ` RETURNING ${params.returning.map(c => `"${c}"`).join(', ')}`;
        }
        
        try {
          const result = await pool.query(query, values);
          return {
            success: true,
            rowCount: result.rowCount,
            rows: result.rows,
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Insert failed: ${error.message}`);
        }
      })
    );

    // Update data
    this.registerTool(
      'postgres_update',
      'Update data in a table',
      UpdateSchema,
      createToolHandler<z.infer<typeof UpdateSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const setColumns = Object.keys(params.data);
        const setValues = Object.values(params.data);
        const queryParams = [...setValues];
        
        const setClause = setColumns.map((col, i) => `"${col}" = $${i + 1}`).join(', ');
        
        const whereClauses = this.buildWhereClause(params.where, queryParams);
        if (whereClauses.length === 0) {
          throw new InvalidParamsError('Update requires at least one WHERE condition');
        }
        
        let query = `UPDATE "${params.schema}"."${params.table}" SET ${setClause} WHERE ${whereClauses.join(' AND ')}`;
        
        if (params.returning && params.returning.length > 0) {
          query += ` RETURNING ${params.returning.map(c => `"${c}"`).join(', ')}`;
        }
        
        try {
          const result = await pool.query(query, queryParams);
          return {
            success: true,
            rowCount: result.rowCount,
            rows: result.rows,
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Update failed: ${error.message}`);
        }
      })
    );

    // Delete data
    this.registerTool(
      'postgres_delete',
      'Delete data from a table',
      DeleteSchema,
      createToolHandler<z.infer<typeof DeleteSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        const queryParams: any[] = [];
        const whereClauses = this.buildWhereClause(params.where, queryParams);
        
        if (whereClauses.length === 0) {
          throw new InvalidParamsError('Delete requires at least one WHERE condition');
        }
        
        let query = `DELETE FROM "${params.schema}"."${params.table}" WHERE ${whereClauses.join(' AND ')}`;
        
        if (params.returning && params.returning.length > 0) {
          query += ` RETURNING ${params.returning.map(c => `"${c}"`).join(', ')}`;
        }
        
        try {
          const result = await pool.query(query, queryParams);
          return {
            success: true,
            rowCount: result.rowCount,
            rows: result.rows,
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Delete failed: ${error.message}`);
        }
      })
    );

    // Select data
    this.registerTool(
      'postgres_select',
      'Select data from a table with optional filtering',
      SelectSchema,
      createToolHandler<z.infer<typeof SelectSchema>>(async (params) => {
        const pool = await this.getPool(params.database);
        
        let query = `SELECT ${params.columns.map(c => c === '*' ? c : `"${c}"`).join(', ')} FROM "${params.schema}"."${params.table}"`;
        const queryParams: any[] = [];
        
        if (params.where && Object.keys(params.where).length > 0) {
          const whereClauses = this.buildWhereClause(params.where, queryParams);
          if (whereClauses.length > 0) {
            query += ` WHERE ${whereClauses.join(' AND ')}`;
          }
        }
        
        if (params.orderBy && params.orderBy.length > 0) {
          const orderClauses = params.orderBy.map(o => `"${o.column}" ${o.direction}`).join(', ');
          query += ` ORDER BY ${orderClauses}`;
        }
        
        if (params.limit !== undefined) {
          query += ` LIMIT ${params.limit}`;
        }
        
        if (params.offset !== undefined) {
          query += ` OFFSET ${params.offset}`;
        }
        
        try {
          const result = await pool.query(query, queryParams);
          return {
            rows: result.rows,
            rowCount: result.rowCount,
          };
        } catch (error: any) {
          throw new InvalidParamsError(`Select failed: ${error.message}`);
        }
      })
    );

    // Database statistics
    this.registerTool(
      'postgres_stats',
      'Get database statistics and connection pool status',
      z.object({
        database: z.string().optional().describe('Database name'),
      }),
      createToolHandler<{ database?: string }>(async (params) => {
        const pool = await this.getPool(params.database);
        const dbName = params.database || this.defaultDatabase || 'postgres';
        
        // Get database size
        const sizeResult = await pool.query(
          "SELECT pg_database_size($1) as size",
          [dbName]
        );
        
        // Get table count
        const tableCountResult = await pool.query(
          "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        );
        
        // Get connection stats
        const connectionResult = await pool.query(
          "SELECT COUNT(*) as active FROM pg_stat_activity WHERE datname = $1",
          [dbName]
        );
        
        return {
          database: dbName,
          size: parseInt(sizeResult.rows[0].size),
          sizeHuman: this.formatBytes(parseInt(sizeResult.rows[0].size)),
          tableCount: parseInt(tableCountResult.rows[0].count),
          activeConnections: parseInt(connectionResult.rows[0].active),
          poolStatus: {
            total: pool.totalCount,
            idle: pool.idleCount,
            waiting: pool.waitingCount,
          },
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

  /**
   * Build WHERE clause with support for MongoDB-style operators
   * Supports: equality, $gte, $gt, $lte, $lt, $ne, $in, $nin
   */
  private buildWhereClause(where: Record<string, any>, queryParams: any[]): string[] {
    const clauses: string[] = [];
    
    for (const [column, condition] of Object.entries(where)) {
      if (condition === null || condition === undefined) {
        // Handle null/undefined as IS NULL
        clauses.push(`"${column}" IS NULL`);
      } else if (typeof condition === 'object' && !Array.isArray(condition) && !(condition instanceof Date)) {
        // Handle operator objects like { $gte: 5, $lt: 10 }
        for (const [operator, value] of Object.entries(condition)) {
          switch (operator) {
            case '$gte':
              queryParams.push(value);
              clauses.push(`"${column}" >= $${queryParams.length}`);
              break;
            case '$gt':
              queryParams.push(value);
              clauses.push(`"${column}" > $${queryParams.length}`);
              break;
            case '$lte':
              queryParams.push(value);
              clauses.push(`"${column}" <= $${queryParams.length}`);
              break;
            case '$lt':
              queryParams.push(value);
              clauses.push(`"${column}" < $${queryParams.length}`);
              break;
            case '$ne':
              if (value === null) {
                clauses.push(`"${column}" IS NOT NULL`);
              } else {
                queryParams.push(value);
                clauses.push(`"${column}" != $${queryParams.length}`);
              }
              break;
            case '$in':
              if (Array.isArray(value) && value.length > 0) {
                const placeholders = value.map((_, i) => {
                  queryParams.push(value[i]);
                  return `$${queryParams.length}`;
                }).join(', ');
                clauses.push(`"${column}" IN (${placeholders})`);
              }
              break;
            case '$nin':
              if (Array.isArray(value) && value.length > 0) {
                const placeholders = value.map((_, i) => {
                  queryParams.push(value[i]);
                  return `$${queryParams.length}`;
                }).join(', ');
                clauses.push(`"${column}" NOT IN (${placeholders})`);
              }
              break;
            default:
              // Ignore unknown operators
              this.logger.warn(`Unknown operator ${operator} for column ${column}`);
          }
        }
      } else {
        // Handle simple equality
        queryParams.push(condition);
        clauses.push(`"${column}" = $${queryParams.length}`);
      }
    }
    
    return clauses;
  }
}