/**
 * Memory MCP Server
 * Provides persistent context and knowledge graph capabilities
 */

import { z } from 'zod';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { promises as fs } from 'fs';
import path from 'path';

// Memory entry types
interface MemoryEntry {
  id: string;
  content: string;
  type: 'fact' | 'preference' | 'experience' | 'goal' | 'context';
  timestamp: Date;
  tags: string[];
  metadata: Record<string, any>;
  relationships: string[]; // IDs of related entries
}

interface MemoryGraph {
  entries: Map<string, MemoryEntry>;
  tags: Map<string, Set<string>>; // tag -> entry IDs
  relationships: Map<string, Set<string>>; // entry ID -> related entry IDs
}

// Input schemas
const StoreMemorySchema = z.object({
  content: z.string().describe('Memory content to store'),
  type: z.enum(['fact', 'preference', 'experience', 'goal', 'context']).describe('Type of memory'),
  tags: z.array(z.string()).default([]).describe('Tags for categorizing the memory'),
  metadata: z.record(z.any()).default({}).describe('Additional metadata'),
  relatedTo: z.array(z.string()).default([]).describe('IDs of related memory entries'),
});

const SearchMemorySchema = z.object({
  query: z.string().describe('Search query'),
  type: z.enum(['fact', 'preference', 'experience', 'goal', 'context']).optional().describe('Filter by memory type'),
  tags: z.array(z.string()).default([]).describe('Filter by tags'),
  limit: z.number().min(1).max(100).default(10).describe('Maximum number of results'),
});

const UpdateMemorySchema = z.object({
  id: z.string().describe('Memory entry ID'),
  content: z.string().optional().describe('Updated content'),
  tags: z.array(z.string()).optional().describe('Updated tags'),
  metadata: z.record(z.any()).optional().describe('Updated metadata'),
  addRelations: z.array(z.string()).default([]).describe('Add relationships to these entry IDs'),
  removeRelations: z.array(z.string()).default([]).describe('Remove relationships to these entry IDs'),
});

export class MemoryServer extends BaseMCPServer {
  private graph: MemoryGraph;
  private dataPath: string;
  private autoSave: boolean = true;
  private saveInterval?: NodeJS.Timeout;

  constructor() {
    super('memory', '1.0.0', 'Persistent memory and knowledge graph for AI context');
    
    this.graph = {
      entries: new Map(),
      tags: new Map(),
      relationships: new Map(),
    };
    
    this.dataPath = path.join(process.cwd(), 'data', 'memory.json');
  }

  protected async onInitialize(): Promise<void> {
    await this.ensureDataDirectory();
    await this.loadMemoryFromDisk();
    
    if (this.autoSave) {
      this.saveInterval = setInterval(() => {
        this.saveMemoryToDisk().catch(error => {
          this.logger.error('Auto-save failed', { error });
        });
      }, 30000); // Save every 30 seconds
    }
    
    this.logger.info('Memory server initialized', {
      entriesCount: this.graph.entries.size,
      tagsCount: this.graph.tags.size,
    });
  }

  protected async onShutdown(): Promise<void> {
    if (this.saveInterval) {
      clearInterval(this.saveInterval);
    }
    
    await this.saveMemoryToDisk();
    this.logger.info('Memory server shut down');
  }

  protected async registerTools(): Promise<void> {
    this.registerTool(
      'memory_store',
      'Store a new memory entry',
      StoreMemorySchema,
      createToolHandler<z.infer<typeof StoreMemorySchema>>(async (params) => {
        const entry = await this.storeMemory(params);
        return {
          id: entry.id,
          stored: true,
          timestamp: entry.timestamp,
        };
      })
    );

    this.registerTool(
      'memory_search',
      'Search memory entries',
      SearchMemorySchema,
      createToolHandler<z.infer<typeof SearchMemorySchema>>(async (params) => {
        return this.searchMemory(params);
      })
    );

    this.registerTool(
      'memory_get',
      'Get a specific memory entry by ID',
      z.object({
        id: z.string().describe('Memory entry ID'),
      }),
      createToolHandler<{ id: string }>(async ({ id }) => {
        const entry = this.graph.entries.get(id);
        if (!entry) {
          throw new Error(`Memory entry not found: ${id}`);
        }
        return this.serializeEntry(entry);
      })
    );

    this.registerTool(
      'memory_update',
      'Update an existing memory entry',
      UpdateMemorySchema,
      createToolHandler<z.infer<typeof UpdateMemorySchema>>(async (params) => {
        return this.updateMemory(params);
      })
    );

    this.registerTool(
      'memory_delete',
      'Delete a memory entry',
      z.object({
        id: z.string().describe('Memory entry ID'),
      }),
      createToolHandler<{ id: string }>(async ({ id }) => {
        return this.deleteMemory(id);
      })
    );

    this.registerTool(
      'memory_list_tags',
      'List all available tags',
      z.object({}),
      createToolHandler(async () => {
        return Array.from(this.graph.tags.entries()).map(([tag, entryIds]) => ({
          tag,
          count: entryIds.size,
        }));
      })
    );

    this.registerTool(
      'memory_get_related',
      'Get entries related to a specific entry',
      z.object({
        id: z.string().describe('Memory entry ID'),
        depth: z.number().min(1).max(3).default(1).describe('Relationship depth'),
      }),
      createToolHandler<{ id: string; depth: number }>(async ({ id, depth }) => {
        return this.getRelatedEntries(id, depth);
      })
    );

    this.registerTool(
      'memory_export',
      'Export memory graph data',
      z.object({
        format: z.enum(['json', 'csv']).default('json'),
      }),
      createToolHandler<{ format: 'json' | 'csv' }>(async ({ format }) => {
        return this.exportMemory(format);
      })
    );
  }

  private async storeMemory(params: z.infer<typeof StoreMemorySchema>): Promise<MemoryEntry> {
    const id = this.generateId();
    const entry: MemoryEntry = {
      id,
      content: params.content,
      type: params.type,
      timestamp: new Date(),
      tags: params.tags,
      metadata: params.metadata,
      relationships: params.relatedTo,
    };

    // Store entry
    this.graph.entries.set(id, entry);

    // Update tag index
    for (const tag of params.tags) {
      if (!this.graph.tags.has(tag)) {
        this.graph.tags.set(tag, new Set());
      }
      this.graph.tags.get(tag)!.add(id);
    }

    // Update relationships
    if (!this.graph.relationships.has(id)) {
      this.graph.relationships.set(id, new Set());
    }
    
    for (const relatedId of params.relatedTo) {
      if (this.graph.entries.has(relatedId)) {
        this.graph.relationships.get(id)!.add(relatedId);
        
        // Bidirectional relationship
        if (!this.graph.relationships.has(relatedId)) {
          this.graph.relationships.set(relatedId, new Set());
        }
        this.graph.relationships.get(relatedId)!.add(id);
      }
    }

    this.logger.debug('Memory stored', { id, type: params.type, tags: params.tags });
    return entry;
  }

  private async searchMemory(params: z.infer<typeof SearchMemorySchema>) {
    const results: MemoryEntry[] = [];
    const query = params.query.toLowerCase();

    for (const entry of this.graph.entries.values()) {
      // Type filter
      if (params.type && entry.type !== params.type) {
        continue;
      }

      // Tag filter
      if (params.tags.length > 0 && !params.tags.some(tag => entry.tags.includes(tag))) {
        continue;
      }

      // Content search
      if (entry.content.toLowerCase().includes(query) ||
          entry.tags.some(tag => tag.toLowerCase().includes(query))) {
        results.push(entry);
      }
    }

    // Sort by relevance (most recent first for now)
    results.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

    return {
      query: params.query,
      totalResults: results.length,
      results: results.slice(0, params.limit).map(entry => this.serializeEntry(entry)),
    };
  }

  private async updateMemory(params: z.infer<typeof UpdateMemorySchema>) {
    const entry = this.graph.entries.get(params.id);
    if (!entry) {
      throw new Error(`Memory entry not found: ${params.id}`);
    }

    // Update content
    if (params.content !== undefined) {
      entry.content = params.content;
    }

    // Update tags
    if (params.tags !== undefined) {
      // Remove old tags
      for (const oldTag of entry.tags) {
        this.graph.tags.get(oldTag)?.delete(params.id);
        if (this.graph.tags.get(oldTag)?.size === 0) {
          this.graph.tags.delete(oldTag);
        }
      }

      // Add new tags
      entry.tags = params.tags;
      for (const newTag of params.tags) {
        if (!this.graph.tags.has(newTag)) {
          this.graph.tags.set(newTag, new Set());
        }
        this.graph.tags.get(newTag)!.add(params.id);
      }
    }

    // Update metadata
    if (params.metadata !== undefined) {
      entry.metadata = { ...entry.metadata, ...params.metadata };
    }

    // Update relationships
    const relationships = this.graph.relationships.get(params.id) || new Set();
    
    for (const addId of params.addRelations) {
      if (this.graph.entries.has(addId)) {
        relationships.add(addId);
        entry.relationships.push(addId);
        
        // Bidirectional
        if (!this.graph.relationships.has(addId)) {
          this.graph.relationships.set(addId, new Set());
        }
        this.graph.relationships.get(addId)!.add(params.id);
      }
    }

    for (const removeId of params.removeRelations) {
      relationships.delete(removeId);
      entry.relationships = entry.relationships.filter(id => id !== removeId);
      
      // Bidirectional
      this.graph.relationships.get(removeId)?.delete(params.id);
    }

    this.graph.relationships.set(params.id, relationships);

    this.logger.debug('Memory updated', { id: params.id });
    return this.serializeEntry(entry);
  }

  private async deleteMemory(id: string) {
    const entry = this.graph.entries.get(id);
    if (!entry) {
      throw new Error(`Memory entry not found: ${id}`);
    }

    // Remove from entries
    this.graph.entries.delete(id);

    // Remove from tag index
    for (const tag of entry.tags) {
      this.graph.tags.get(tag)?.delete(id);
      if (this.graph.tags.get(tag)?.size === 0) {
        this.graph.tags.delete(tag);
      }
    }

    // Remove from relationships
    const relationships = this.graph.relationships.get(id);
    if (relationships) {
      for (const relatedId of relationships) {
        this.graph.relationships.get(relatedId)?.delete(id);
      }
      this.graph.relationships.delete(id);
    }

    this.logger.debug('Memory deleted', { id });
    return { id, deleted: true };
  }

  private getRelatedEntries(id: string, depth: number) {
    const visited = new Set<string>();
    const results = new Map<string, MemoryEntry>();

    const traverse = (entryId: string, currentDepth: number) => {
      if (currentDepth > depth || visited.has(entryId)) {
        return;
      }

      visited.add(entryId);
      const entry = this.graph.entries.get(entryId);
      if (entry) {
        results.set(entryId, entry);
        
        const relationships = this.graph.relationships.get(entryId);
        if (relationships && currentDepth < depth) {
          for (const relatedId of relationships) {
            traverse(relatedId, currentDepth + 1);
          }
        }
      }
    };

    traverse(id, 0);
    results.delete(id); // Remove the original entry

    return {
      id,
      depth,
      relatedEntries: Array.from(results.values()).map(entry => this.serializeEntry(entry)),
    };
  }

  private async exportMemory(format: 'json' | 'csv') {
    if (format === 'json') {
      return {
        format: 'json',
        data: {
          entries: Array.from(this.graph.entries.values()).map(entry => this.serializeEntry(entry)),
          stats: {
            totalEntries: this.graph.entries.size,
            totalTags: this.graph.tags.size,
            totalRelationships: Array.from(this.graph.relationships.values())
              .reduce((sum, relations) => sum + relations.size, 0),
          },
        },
      };
    } else {
      // CSV format
      const entries = Array.from(this.graph.entries.values());
      const csvData = entries.map(entry => ({
        id: entry.id,
        content: entry.content.replace(/"/g, '""'), // Escape quotes
        type: entry.type,
        timestamp: entry.timestamp.toISOString(),
        tags: entry.tags.join(';'),
        relationships: entry.relationships.join(';'),
      }));

      return {
        format: 'csv',
        headers: ['id', 'content', 'type', 'timestamp', 'tags', 'relationships'],
        data: csvData,
      };
    }
  }

  private serializeEntry(entry: MemoryEntry) {
    return {
      id: entry.id,
      content: entry.content,
      type: entry.type,
      timestamp: entry.timestamp.toISOString(),
      tags: entry.tags,
      metadata: entry.metadata,
      relationships: entry.relationships,
    };
  }

  private generateId(): string {
    return `mem_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private async ensureDataDirectory(): Promise<void> {
    const dataDir = path.dirname(this.dataPath);
    try {
      await fs.mkdir(dataDir, { recursive: true });
    } catch (error) {
      // Directory might already exist
    }
  }

  private async loadMemoryFromDisk(): Promise<void> {
    try {
      const data = await fs.readFile(this.dataPath, 'utf-8');
      const saved = JSON.parse(data);
      
      // Restore entries
      for (const entryData of saved.entries || []) {
        const entry: MemoryEntry = {
          ...entryData,
          timestamp: new Date(entryData.timestamp),
        };
        this.graph.entries.set(entry.id, entry);
      }

      // Rebuild indexes
      this.rebuildIndexes();
      
      this.logger.info('Memory loaded from disk', {
        entries: this.graph.entries.size,
      });
    } catch (error) {
      if ((error as any).code === 'ENOENT') {
        this.logger.info('No existing memory file found, starting fresh');
      } else {
        this.logger.error('Failed to load memory from disk', { error });
      }
    }
  }

  private async saveMemoryToDisk(): Promise<void> {
    try {
      const data = {
        version: '1.0.0',
        timestamp: new Date().toISOString(),
        entries: Array.from(this.graph.entries.values()),
      };
      
      await fs.writeFile(this.dataPath, JSON.stringify(data, null, 2));
      this.logger.debug('Memory saved to disk');
    } catch (error) {
      this.logger.error('Failed to save memory to disk', { error });
    }
  }

  private rebuildIndexes(): void {
    this.graph.tags.clear();
    this.graph.relationships.clear();

    for (const entry of this.graph.entries.values()) {
      // Rebuild tag index
      for (const tag of entry.tags) {
        if (!this.graph.tags.has(tag)) {
          this.graph.tags.set(tag, new Set());
        }
        this.graph.tags.get(tag)!.add(entry.id);
      }

      // Rebuild relationship index
      if (!this.graph.relationships.has(entry.id)) {
        this.graph.relationships.set(entry.id, new Set());
      }
      
      for (const relatedId of entry.relationships) {
        this.graph.relationships.get(entry.id)!.add(relatedId);
      }
    }
  }
}