/**
 * Filesystem MCP Server
 * Provides secure file operations with path sandboxing and file watching
 */

import { z } from 'zod';
import { promises as fs, constants } from 'fs';
import { watch, FSWatcher } from 'chokidar';
import path from 'path';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { config } from '../../src/utils/config';
import { PermissionError, ResourceNotFoundError, InvalidParamsError } from '../../src/utils/errors';

// Input schemas
const FilePathSchema = z.object({
  path: z.string().describe('File path (relative to allowed directories)'),
});

const ReadFileSchema = z.object({
  path: z.string().describe('File path to read'),
  encoding: z.enum(['utf8', 'base64', 'binary']).default('utf8').describe('File encoding'),
  offset: z.number().optional().describe('Start reading from this byte offset'),
  length: z.number().optional().describe('Number of bytes to read'),
});

const WriteFileSchema = z.object({
  path: z.string().describe('File path to write'),
  content: z.string().describe('Content to write to file'),
  encoding: z.enum(['utf8', 'base64', 'binary']).default('utf8').describe('Content encoding'),
  createDirs: z.boolean().default(true).describe('Create parent directories if they don\'t exist'),
  mode: z.number().optional().describe('File permissions (octal)'),
});

const CopyFileSchema = z.object({
  source: z.string().describe('Source file path'),
  destination: z.string().describe('Destination file path'),
  overwrite: z.boolean().default(false).describe('Overwrite destination if it exists'),
  createDirs: z.boolean().default(true).describe('Create parent directories'),
});

const MoveFileSchema = z.object({
  source: z.string().describe('Source file path'),
  destination: z.string().describe('Destination file path'),
  overwrite: z.boolean().default(false).describe('Overwrite destination if it exists'),
  createDirs: z.boolean().default(true).describe('Create parent directories'),
});

const ListDirectorySchema = z.object({
  path: z.string().describe('Directory path to list'),
  recursive: z.boolean().default(false).describe('List subdirectories recursively'),
  includeHidden: z.boolean().default(false).describe('Include hidden files (starting with .)'),
  pattern: z.string().optional().describe('Glob pattern to filter files'),
  details: z.boolean().default(false).describe('Include file details (size, dates, permissions)'),
});

const CreateDirectorySchema = z.object({
  path: z.string().describe('Directory path to create'),
  recursive: z.boolean().default(true).describe('Create parent directories if needed'),
  mode: z.number().optional().describe('Directory permissions (octal)'),
});

const WatchPathSchema = z.object({
  path: z.string().describe('Path to watch for changes'),
  recursive: z.boolean().default(true).describe('Watch subdirectories recursively'),
  events: z.array(z.enum(['add', 'change', 'unlink', 'addDir', 'unlinkDir'])).default(['change']).describe('Events to watch for'),
});

const SearchFilesSchema = z.object({
  path: z.string().describe('Directory to search in'),
  query: z.string().describe('Search query (file content or name)'),
  filePattern: z.string().optional().describe('File name pattern (glob)'),
  searchContent: z.boolean().default(true).describe('Search file contents'),
  searchNames: z.boolean().default(true).describe('Search file names'),
  caseSensitive: z.boolean().default(false).describe('Case sensitive search'),
  maxResults: z.number().default(100).describe('Maximum number of results'),
});

interface FileWatcher {
  id: string;
  path: string;
  watcher: FSWatcher;
  events: string[];
  created: Date;
}

export class FilesystemServer extends BaseMCPServer {
  private allowedPaths: string[];
  private blockedPaths: string[];
  private maxFileSize: number;
  private watchers: Map<string, FileWatcher>;
  private watcherCounter: number = 0;
  private trackFileOperations: boolean = true;

  constructor() {
    super('filesystem', '1.0.0', 'Secure filesystem operations with path sandboxing');
    
    this.allowedPaths = config.getAllowedPaths();
    this.blockedPaths = ['/etc', '/var', '/usr', '/bin', '/sbin', '/boot', '/sys', '/proc'];
    this.maxFileSize = config.getMaxFileSize();
    this.watchers = new Map();
  }

  protected async onInitialize(): Promise<void> {
    this.logger.info('Filesystem server initialized', {
      allowedPaths: this.allowedPaths,
      maxFileSize: this.maxFileSize,
    });
  }

  protected async onShutdown(): Promise<void> {
    // Clean up watchers
    for (const watcher of this.watchers.values()) {
      await watcher.watcher.close();
    }
    this.watchers.clear();
  }

  protected async registerTools(): Promise<void> {
    // File operations
    this.registerTool(
      'fs_read_file',
      'Read contents of a file',
      ReadFileSchema,
      createToolHandler<any>(async (params) => {
        return this.readFile(params);
      })
    );

    this.registerTool(
      'fs_write_file',
      'Write content to a file',
      WriteFileSchema,
      createToolHandler<any>(async (params) => {
        return this.writeFile(params);
      })
    );

    this.registerTool(
      'fs_delete_file',
      'Delete a file',
      FilePathSchema,
      createToolHandler<any>(async ({ path: filePath }) => {
        return this.deleteFile(filePath);
      })
    );

    this.registerTool(
      'fs_copy_file',
      'Copy a file to another location',
      CopyFileSchema,
      createToolHandler<any>(async (params) => {
        return this.copyFile(params);
      })
    );

    this.registerTool(
      'fs_move_file',
      'Move/rename a file',
      MoveFileSchema,
      createToolHandler<any>(async (params) => {
        return this.moveFile(params);
      })
    );

    // Directory operations
    this.registerTool(
      'fs_list_directory',
      'List contents of a directory',
      ListDirectorySchema,
      createToolHandler<any>(async (params) => {
        return this.listDirectory(params);
      })
    );

    this.registerTool(
      'fs_create_directory',
      'Create a directory',
      CreateDirectorySchema,
      createToolHandler<any>(async (params) => {
        return this.createDirectory(params);
      })
    );

    this.registerTool(
      'fs_delete_directory',
      'Delete a directory',
      z.object({
        path: z.string().describe('Directory path to delete'),
        recursive: z.boolean().default(false).describe('Delete recursively (dangerous!)'),
      }),
      createToolHandler<any>(async ({ path: dirPath, recursive }) => {
        return this.deleteDirectory(dirPath, recursive);
      })
    );

    // File information
    this.registerTool(
      'fs_get_stats',
      'Get file or directory statistics',
      FilePathSchema,
      createToolHandler<any>(async ({ path: filePath }) => {
        return this.getStats(filePath);
      })
    );

    this.registerTool(
      'fs_exists',
      'Check if a file or directory exists',
      FilePathSchema,
      createToolHandler<any>(async ({ path: filePath }) => {
        const absolutePath = this.resolvePath(filePath);
        this.validatePath(absolutePath);

        try {
          await fs.access(absolutePath);
          return { exists: true, path: filePath };
        } catch {
          return { exists: false, path: filePath };
        }
      })
    );

    // File watching
    this.registerTool(
      'fs_watch_path',
      'Watch a path for file system changes',
      WatchPathSchema,
      createToolHandler<any>(async (params) => {
        return this.watchPath(params);
      })
    );

    this.registerTool(
      'fs_unwatch_path',
      'Stop watching a path',
      z.object({
        watcherId: z.string().describe('Watcher ID returned from fs_watch_path'),
      }),
      createToolHandler<any>(async ({ watcherId }) => {
        return this.unwatchPath(watcherId);
      })
    );

    this.registerTool(
      'fs_list_watchers',
      'List active file watchers',
      z.object({}),
      createToolHandler(async () => {
        return this.listWatchers();
      })
    );

    // Search
    this.registerTool(
      'fs_search_files',
      'Search for files by name or content',
      SearchFilesSchema,
      createToolHandler<any>(async (params) => {
        return this.searchFiles(params);
      })
    );

    // Utility operations
    this.registerTool(
      'fs_get_working_directory',
      'Get current working directory',
      z.object({}),
      createToolHandler(async () => {
        return {
          cwd: process.cwd(),
          allowed: this.allowedPaths,
        };
      })
    );
  }

  private resolvePath(inputPath: string): string {
    // Handle both absolute and relative paths
    if (path.isAbsolute(inputPath)) {
      return path.resolve(inputPath);
    }
    
    // For relative paths, resolve against the first allowed directory
    const basePath = this.allowedPaths[0] || process.cwd();
    return path.resolve(basePath, inputPath);
  }

  private validatePath(absolutePath: string): void {
    // Check if path is within allowed directories
    const isAllowed = this.allowedPaths.some(allowedPath => {
      const resolvedAllowed = path.resolve(allowedPath);
      return absolutePath.startsWith(resolvedAllowed);
    });

    if (!isAllowed) {
      throw new PermissionError(absolutePath, 'access');
    }

    // Check if path is in blocked directories
    const isBlocked = this.blockedPaths.some(blockedPath => {
      return absolutePath.startsWith(blockedPath);
    });

    if (isBlocked) {
      throw new PermissionError(absolutePath, 'access (blocked directory)');
    }

    // Additional security checks
    if (absolutePath.includes('..')) {
      throw new PermissionError(absolutePath, 'access (path traversal attempt)');
    }
  }

  private async readFile(params: z.infer<typeof ReadFileSchema>) {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    try {
      // Check file size
      const stats = await fs.stat(absolutePath);
      if (stats.size > this.maxFileSize) {
        throw new InvalidParamsError(`File too large: ${stats.size} bytes (max: ${this.maxFileSize})`);
      }

      // Read file with options
      const options: any = { encoding: params.encoding };
      if (params.offset !== undefined || params.length !== undefined) {
        // For partial reads, we need to use a different approach
        const buffer = Buffer.alloc(params.length || stats.size);
        const fd = await fs.open(absolutePath, 'r');
        
        try {
          const result = await fd.read(buffer, 0, params.length || stats.size, params.offset || 0);
          await fd.close();
          
          const content = params.encoding === 'utf8' 
            ? buffer.toString('utf8', 0, result.bytesRead)
            : buffer.toString(params.encoding as BufferEncoding, 0, result.bytesRead);
            
          return {
            path: params.path,
            content,
            size: result.bytesRead,
            encoding: params.encoding,
          };
        } finally {
          await fd.close().catch(() => {});
        }
      } else {
        const content = await fs.readFile(absolutePath, options);
        return {
          path: params.path,
          content,
          size: stats.size,
          encoding: params.encoding,
        };
      }
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        throw new ResourceNotFoundError(params.path);
      }
      throw error;
    }
  }

  private async writeFile(params: z.infer<typeof WriteFileSchema>) {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    // Create parent directories if needed
    if (params.createDirs) {
      const parentDir = path.dirname(absolutePath);
      await fs.mkdir(parentDir, { recursive: true });
    }

    // Check content size
    const contentSize = Buffer.byteLength(params.content, params.encoding as BufferEncoding);
    if (contentSize > this.maxFileSize) {
      throw new InvalidParamsError(`Content too large: ${contentSize} bytes (max: ${this.maxFileSize})`);
    }

    const options: any = { encoding: params.encoding };
    if (params.mode !== undefined) {
      options.mode = params.mode;
    }

    await fs.writeFile(absolutePath, params.content, options);

    const stats = await fs.stat(absolutePath);
    
    // Track file operation in memory if enabled
    if (this.trackFileOperations) {
      await this.trackFileOperation('write', params.path, {
        size: stats.size,
        encoding: params.encoding,
        createDirs: params.createDirs,
      });
    }

    return {
      path: params.path,
      size: stats.size,
      created: stats.birthtime,
      modified: stats.mtime,
    };
  }

  private async deleteFile(filePath: string) {
    const absolutePath = this.resolvePath(filePath);
    this.validatePath(absolutePath);

    try {
      const stats = await fs.stat(absolutePath);
      if (stats.isDirectory()) {
        throw new InvalidParamsError('Cannot delete directory with fs_delete_file, use fs_delete_directory');
      }

      await fs.unlink(absolutePath);
      return {
        path: filePath,
        deleted: true,
      };
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        throw new ResourceNotFoundError(filePath);
      }
      throw error;
    }
  }

  private async copyFile(params: z.infer<typeof CopyFileSchema>) {
    const sourcePath = this.resolvePath(params.source);
    const destPath = this.resolvePath(params.destination);
    
    this.validatePath(sourcePath);
    this.validatePath(destPath);

    // Create parent directories if needed
    if (params.createDirs) {
      const parentDir = path.dirname(destPath);
      await fs.mkdir(parentDir, { recursive: true });
    }

    // Check if destination exists
    if (!params.overwrite) {
      try {
        await fs.access(destPath);
        throw new InvalidParamsError('Destination file exists and overwrite is false');
      } catch (error: any) {
        if (error.code !== 'ENOENT') {
          throw error;
        }
      }
    }

    await fs.copyFile(sourcePath, destPath);

    const stats = await fs.stat(destPath);
    return {
      source: params.source,
      destination: params.destination,
      size: stats.size,
      copied: true,
    };
  }

  private async moveFile(params: z.infer<typeof MoveFileSchema>) {
    const sourcePath = this.resolvePath(params.source);
    const destPath = this.resolvePath(params.destination);
    
    this.validatePath(sourcePath);
    this.validatePath(destPath);

    // Create parent directories if needed
    if (params.createDirs) {
      const parentDir = path.dirname(destPath);
      await fs.mkdir(parentDir, { recursive: true });
    }

    // Check if destination exists
    if (!params.overwrite) {
      try {
        await fs.access(destPath);
        throw new InvalidParamsError('Destination file exists and overwrite is false');
      } catch (error: any) {
        if (error.code !== 'ENOENT') {
          throw error;
        }
      }
    }

    await fs.rename(sourcePath, destPath);

    const stats = await fs.stat(destPath);
    return {
      source: params.source,
      destination: params.destination,
      size: stats.size,
      moved: true,
    };
  }

  private async listDirectory(params: z.infer<typeof ListDirectorySchema>): Promise<any> {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    try {
      const entries = await fs.readdir(absolutePath);
      const results = [];

      for (const entry of entries) {
        // Skip hidden files if not requested
        if (!params.includeHidden && entry.startsWith('.')) {
          continue;
        }

        const entryPath = path.join(absolutePath, entry);
        const relativePath = path.join(params.path, entry);

        try {
          const stats = await fs.stat(entryPath);
          const item: any = {
            name: entry,
            path: relativePath,
            type: stats.isDirectory() ? 'directory' : 'file',
          };

          if (params.details) {
            item.size = stats.size;
            item.created = stats.birthtime;
            item.modified = stats.mtime;
            item.permissions = stats.mode;
            item.isReadable = await this.checkAccess(entryPath, constants.R_OK);
            item.isWritable = await this.checkAccess(entryPath, constants.W_OK);
          }

          results.push(item);

          // Recursive listing for directories
          if (params.recursive && stats.isDirectory()) {
            try {
              const subItems: any = await this.listDirectory({
                path: relativePath,
                recursive: true,
                includeHidden: params.includeHidden,
                pattern: params.pattern,
                details: params.details,
              });
              results.push(...(subItems as any).items);
            } catch (error) {
              // Skip directories we can't read
              this.logger.warn('Cannot read subdirectory', { path: relativePath, error });
            }
          }
        } catch (error) {
          // Skip items we can't stat
          this.logger.warn('Cannot stat file', { path: relativePath, error });
        }
      }

      // Apply pattern filter if specified
      let filteredResults: any = results;
      if (params.pattern) {
        const minimatch = await import('minimatch');
        filteredResults = results.filter(item => 
          minimatch.minimatch(item.name, params.pattern!)
        );
      }

      return {
        path: params.path,
        items: filteredResults,
        count: filteredResults.length,
      };
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        throw new ResourceNotFoundError(params.path);
      }
      if (error.code === 'ENOTDIR') {
        throw new InvalidParamsError('Path is not a directory');
      }
      throw error;
    }
  }

  private async createDirectory(params: z.infer<typeof CreateDirectorySchema>) {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    const options: any = { recursive: params.recursive };
    if (params.mode !== undefined) {
      options.mode = params.mode;
    }

    await fs.mkdir(absolutePath, options);

    const stats = await fs.stat(absolutePath);
    return {
      path: params.path,
      created: true,
      permissions: stats.mode,
    };
  }

  private async deleteDirectory(dirPath: string, recursive: boolean) {
    const absolutePath = this.resolvePath(dirPath);
    this.validatePath(absolutePath);

    try {
      const stats = await fs.stat(absolutePath);
      if (!stats.isDirectory()) {
        throw new InvalidParamsError('Path is not a directory');
      }

      if (recursive) {
        await fs.rm(absolutePath, { recursive: true, force: true });
      } else {
        await fs.rmdir(absolutePath);
      }

      return {
        path: dirPath,
        deleted: true,
        recursive,
      };
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        throw new ResourceNotFoundError(dirPath);
      }
      if (error.code === 'ENOTEMPTY') {
        throw new InvalidParamsError('Directory not empty (use recursive: true to force delete)');
      }
      throw error;
    }
  }

  private async getStats(filePath: string) {
    const absolutePath = this.resolvePath(filePath);
    this.validatePath(absolutePath);

    try {
      const stats = await fs.stat(absolutePath);
      return {
        path: filePath,
        type: stats.isDirectory() ? 'directory' : 'file',
        size: stats.size,
        created: stats.birthtime,
        modified: stats.mtime,
        accessed: stats.atime,
        permissions: stats.mode,
        uid: stats.uid,
        gid: stats.gid,
        isReadable: await this.checkAccess(absolutePath, constants.R_OK),
        isWritable: await this.checkAccess(absolutePath, constants.W_OK),
        isExecutable: await this.checkAccess(absolutePath, constants.X_OK),
      };
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        throw new ResourceNotFoundError(filePath);
      }
      throw error;
    }
  }

  private async watchPath(params: z.infer<typeof WatchPathSchema>) {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    const watcherId = `watcher-${++this.watcherCounter}`;
    
    const watcher = watch(absolutePath, {
      persistent: true,
      ignoreInitial: true,
    });

    // Set up event listeners
    params.events.forEach(eventType => {
      watcher.on(eventType, (filePath) => {
        this.logger.info('File system event', {
          watcherId,
          event: eventType,
          path: filePath,
        });

        // In a real implementation, you might want to emit these events
        // to connected clients or store them for later retrieval
      });
    });

    const watcherInfo: FileWatcher = {
      id: watcherId,
      path: params.path,
      watcher,
      events: params.events,
      created: new Date(),
    };

    this.watchers.set(watcherId, watcherInfo);

    return {
      watcherId,
      path: params.path,
      events: params.events,
      recursive: params.recursive,
    };
  }

  private async unwatchPath(watcherId: string) {
    const watcher = this.watchers.get(watcherId);
    if (!watcher) {
      throw new ResourceNotFoundError(`Watcher ${watcherId}`);
    }

    await watcher.watcher.close();
    this.watchers.delete(watcherId);

    return {
      watcherId,
      stopped: true,
    };
  }

  private async listWatchers() {
    return {
      watchers: Array.from(this.watchers.values()).map(w => ({
        id: w.id,
        path: w.path,
        events: w.events,
        created: w.created,
      })),
      count: this.watchers.size,
    };
  }

  private async searchFiles(params: z.infer<typeof SearchFilesSchema>) {
    const absolutePath = this.resolvePath(params.path);
    this.validatePath(absolutePath);

    const results: any[] = [];
    const query = params.caseSensitive ? params.query : params.query.toLowerCase();

    async function searchInDirectory(dirPath: string, relativePath: string) {
      try {
        const entries = await fs.readdir(dirPath);

        for (const entry of entries) {
          const entryPath = path.join(dirPath, entry);
          const entryRelativePath = path.join(relativePath, entry);

          try {
            const stats = await fs.stat(entryPath);

            if (stats.isDirectory()) {
              // Recursively search subdirectories
              await searchInDirectory(entryPath, entryRelativePath);
            } else if (stats.isFile()) {
              let matches = false;

              // Search file names
              if (params.searchNames) {
                const fileName = params.caseSensitive ? entry : entry.toLowerCase();
                if (fileName.includes(query)) {
                  matches = true;
                }
              }

              // Search file contents (for text files)
              if (params.searchContent && !matches && stats.size < 1024 * 1024) { // Max 1MB
                try {
                  const content = await fs.readFile(entryPath, 'utf8');
                  const searchContent = params.caseSensitive ? content : content.toLowerCase();
                  if (searchContent.includes(query)) {
                    matches = true;
                  }
                } catch (error) {
                  // Skip binary files or files we can't read
                }
              }

              // Apply file pattern filter
              if (matches && params.filePattern) {
                const minimatch = await import('minimatch');
                matches = minimatch.minimatch(entry, params.filePattern);
              }

              if (matches) {
                results.push({
                  path: entryRelativePath,
                  name: entry,
                  size: stats.size,
                  modified: stats.mtime,
                  type: 'file',
                });

                if (results.length >= params.maxResults) {
                  return;
                }
              }
            }
          } catch (error) {
            // Skip files we can't access
          }
        }
      } catch (error) {
        // Skip directories we can't read
      }
    }

    await searchInDirectory(absolutePath, params.path);

    return {
      query: params.query,
      path: params.path,
      results,
      count: results.length,
      maxResults: params.maxResults,
    };
  }

  private async checkAccess(filePath: string, mode: number): Promise<boolean> {
    try {
      await fs.access(filePath, mode);
      return true;
    } catch {
      return false;
    }
  }

  private async trackFileOperation(operation: string, filePath: string, metadata: any = {}) {
    try {
      // In a real implementation, this would communicate with the Memory server
      // For now, we'll log the operation and prepare the data structure
      const operationRecord = {
        operation,
        path: filePath,
        timestamp: new Date().toISOString(),
        metadata,
        server: 'filesystem',
      };

      this.logger.debug('File operation tracked', operationRecord);

      // This would ideally make a request to the Memory server to store context
      // await this.memoryClient.store({
      //   content: `File operation: ${operation} on ${filePath}`,
      //   type: 'experience',
      //   tags: ['filesystem', operation, path.extname(filePath)],
      //   metadata: operationRecord
      // });

      return operationRecord;
    } catch (error) {
      this.logger.error('Failed to track file operation', { error, operation, filePath });
      return null;
    }
  }

  protected getCustomMethods(): string[] {
    return ['getRecentOperations', 'toggleOperationTracking'];
  }

  protected async handleCustomMethod(method: string, params: unknown): Promise<unknown> {
    switch (method) {
      case 'getRecentOperations':
        return this.getRecentOperations();
      case 'toggleOperationTracking':
        return this.toggleOperationTracking(params as any);
      default:
        return super.handleCustomMethod(method, params);
    }
  }

  private async getRecentOperations() {
    // In a real implementation, this would query the Memory server
    // For now, return placeholder data
    return {
      message: 'Operation tracking is active',
      trackingEnabled: this.trackFileOperations,
      note: 'Detailed operation history would be retrieved from Memory server'
    };
  }

  private async toggleOperationTracking(params: { enabled?: boolean } = {}) {
    if (params.enabled !== undefined) {
      this.trackFileOperations = params.enabled;
    } else {
      this.trackFileOperations = !this.trackFileOperations;
    }

    return {
      trackingEnabled: this.trackFileOperations,
      changed: true,
    };
  }
}