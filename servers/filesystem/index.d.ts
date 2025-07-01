/**
 * Filesystem MCP Server
 * Provides secure file operations with path sandboxing and file watching
 */
import { BaseMCPServer } from '../../src/core/base-server';
export declare class FilesystemServer extends BaseMCPServer {
    private allowedPaths;
    private blockedPaths;
    private maxFileSize;
    private watchers;
    private watcherCounter;
    private trackFileOperations;
    constructor();
    protected onInitialize(): Promise<void>;
    protected onShutdown(): Promise<void>;
    protected registerTools(): Promise<void>;
    private resolvePath;
    private validatePath;
    private readFile;
    private writeFile;
    private deleteFile;
    private copyFile;
    private moveFile;
    private listDirectory;
    private createDirectory;
    private deleteDirectory;
    private getStats;
    private watchPath;
    private unwatchPath;
    private listWatchers;
    private searchFiles;
    private checkAccess;
    private trackFileOperation;
    protected getCustomMethods(): string[];
    protected handleCustomMethod(method: string, params: unknown): Promise<unknown>;
    private getRecentOperations;
    private toggleOperationTracking;
}
//# sourceMappingURL=index.d.ts.map