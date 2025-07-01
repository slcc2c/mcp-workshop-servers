/**
 * Docker MCP Server
 * Provides container management with resource limits and isolation
 */
import { BaseMCPServer } from '../../src/core/base-server';
export declare class DockerServer extends BaseMCPServer {
    private docker;
    private defaultLimits;
    private allowedImages;
    private trackOperations;
    constructor();
    protected onInitialize(): Promise<void>;
    protected onShutdown(): Promise<void>;
    protected registerTools(): Promise<void>;
    private validateImage;
    private parseResourceLimit;
    private createContainer;
    private startContainer;
    private stopContainer;
    private removeContainer;
    private restartContainer;
    private listContainers;
    private inspectContainer;
    private getContainerLogs;
    private getContainerStats;
    private execInContainer;
    private listImages;
    private pullImage;
    private buildImage;
    private removeImage;
    private createVolume;
    private listVolumes;
    private removeVolume;
    private createNetwork;
    private listNetworks;
    private removeNetwork;
    private getSystemInfo;
    private systemPrune;
    private trackOperation;
    protected getCustomMethods(): string[];
    protected handleCustomMethod(method: string, params: unknown): Promise<unknown>;
    private getOperationHistory;
    private toggleOperationTracking;
    private updateResourceLimits;
}
//# sourceMappingURL=index.d.ts.map