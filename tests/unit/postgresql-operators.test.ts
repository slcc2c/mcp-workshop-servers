import { describe, it, expect, beforeEach } from 'vitest';
import { PostgreSQLServer } from '../../servers/postgresql';

describe('PostgreSQL Query Operators Unit Tests', () => {
  let server: PostgreSQLServer;
  
  beforeEach(() => {
    server = new PostgreSQLServer();
  });

  describe('buildWhereClause', () => {
    it('should handle simple equality', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ name: 'John', age: 25 }, queryParams);
      
      expect(clauses).toEqual(['"name" = $1', '"age" = $2']);
      expect(queryParams).toEqual(['John', 25]);
    });

    it('should handle $gte operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ age: { $gte: 18 } }, queryParams);
      
      expect(clauses).toEqual(['"age" >= $1']);
      expect(queryParams).toEqual([18]);
    });

    it('should handle $gt operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ score: { $gt: 90 } }, queryParams);
      
      expect(clauses).toEqual(['"score" > $1']);
      expect(queryParams).toEqual([90]);
    });

    it('should handle $lte operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ price: { $lte: 100 } }, queryParams);
      
      expect(clauses).toEqual(['"price" <= $1']);
      expect(queryParams).toEqual([100]);
    });

    it('should handle $lt operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ temperature: { $lt: 32 } }, queryParams);
      
      expect(clauses).toEqual(['"temperature" < $1']);
      expect(queryParams).toEqual([32]);
    });

    it('should handle $ne operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ status: { $ne: 'inactive' } }, queryParams);
      
      expect(clauses).toEqual(['"status" != $1']);
      expect(queryParams).toEqual(['inactive']);
    });

    it('should handle $ne with null', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ email: { $ne: null } }, queryParams);
      
      expect(clauses).toEqual(['"email" IS NOT NULL']);
      expect(queryParams).toEqual([]);
    });

    it('should handle $in operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ 
        category: { $in: ['electronics', 'books', 'clothing'] } 
      }, queryParams);
      
      expect(clauses).toEqual(['"category" IN ($1, $2, $3)']);
      expect(queryParams).toEqual(['electronics', 'books', 'clothing']);
    });

    it('should handle $nin operator', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ 
        role: { $nin: ['admin', 'superuser'] } 
      }, queryParams);
      
      expect(clauses).toEqual(['"role" NOT IN ($1, $2)']);
      expect(queryParams).toEqual(['admin', 'superuser']);
    });

    it('should handle null values', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ deleted_at: null }, queryParams);
      
      expect(clauses).toEqual(['"deleted_at" IS NULL']);
      expect(queryParams).toEqual([]);
    });

    it('should handle multiple operators on same field', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ 
        age: { $gte: 18, $lt: 65 } 
      }, queryParams);
      
      expect(clauses).toContain('"age" >= $1');
      expect(clauses).toContain('"age" < $2');
      expect(queryParams).toEqual([18, 65]);
    });

    it('should handle complex queries with multiple fields', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({
        name: 'John',
        age: { $gte: 18, $lte: 65 },
        status: { $in: ['active', 'pending'] },
        deleted_at: null
      }, queryParams);
      
      expect(clauses).toContain('"name" = $1');
      expect(clauses).toContain('"age" >= $2');
      expect(clauses).toContain('"age" <= $3');
      expect(clauses).toContain('"status" IN ($4, $5)');
      expect(clauses).toContain('"deleted_at" IS NULL');
      expect(queryParams).toEqual(['John', 18, 65, 'active', 'pending']);
    });

    it('should preserve parameter order across multiple calls', () => {
      const queryParams: any[] = ['existing', 'params'];
      const clauses = (server as any).buildWhereClause({ 
        name: 'Alice',
        score: { $gt: 80 }
      }, queryParams);
      
      expect(clauses).toEqual(['"name" = $3', '"score" > $4']);
      expect(queryParams).toEqual(['existing', 'params', 'Alice', 80]);
    });

    it('should handle Date objects as simple values', () => {
      const queryParams: any[] = [];
      const date = new Date('2023-01-01');
      const clauses = (server as any).buildWhereClause({ created_at: date }, queryParams);
      
      expect(clauses).toEqual(['"created_at" = $1']);
      expect(queryParams).toEqual([date]);
    });

    it('should handle arrays as simple values', () => {
      const queryParams: any[] = [];
      const tags = ['javascript', 'typescript'];
      const clauses = (server as any).buildWhereClause({ tags: tags }, queryParams);
      
      expect(clauses).toEqual(['"tags" = $1']);
      expect(queryParams).toEqual([tags]);
    });

    it('should ignore empty $in arrays', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ 
        category: { $in: [] } 
      }, queryParams);
      
      expect(clauses).toEqual([]);
      expect(queryParams).toEqual([]);
    });

    it('should ignore empty $nin arrays', () => {
      const queryParams: any[] = [];
      const clauses = (server as any).buildWhereClause({ 
        role: { $nin: [] } 
      }, queryParams);
      
      expect(clauses).toEqual([]);
      expect(queryParams).toEqual([]);
    });
  });
});