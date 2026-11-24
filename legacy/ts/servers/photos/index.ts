import { promises as fs } from 'fs';
import path from 'path';
import { z } from 'zod';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server.js';
import { MCPErrorCode } from '../../src/types/mcp.js';
import { MCPServerError } from '../../src/utils/errors.js';
import {
  OsaScriptPhotosRunner,
  PhotosOperation,
  PhotosScriptError,
  PhotosScriptRunner,
} from './photos-osascript.js';

const IsoDateSchema = z
  .string()
  .min(1)
  .refine((value) => !Number.isNaN(Date.parse(value)), {
    message: 'Expected an ISO date string',
  });

const ListAlbumsSchema = z.object({
  includeSmart: z.boolean().default(true),
  limit: z.number().int().min(1).max(500).default(200),
  offset: z.number().int().min(0).default(0),
});

const SearchAssetsSchema = z.object({
  query: z.string().optional(),
  albumId: z.string().optional(),
  dateFrom: IsoDateSchema.optional(),
  dateTo: IsoDateSchema.optional(),
  isFavorite: z.boolean().optional(),
  isHidden: z.boolean().optional(),
  mediaType: z.enum(['image', 'video', 'any']).default('any'),
  limit: z.number().int().min(1).max(500).default(100),
  offset: z.number().int().min(0).default(0),
  sort: z.enum(['created_desc', 'created_asc']).default('created_desc'),
});

const GetAssetSchema = z.object({
  assetId: z.string().min(1),
});

const ExportAssetsSchema = z.object({
  assetIds: z.array(z.string().min(1)).min(1).max(500),
  destinationSubdir: z.string().default('exports'),
  overwrite: z.boolean().default(false),
  exportVariant: z.enum(['original', 'current']).default('current'),
});

const LocationSchema = z.object({
  latitude: z.number(),
  longitude: z.number(),
});

const RichAssetSchema = z.object({
  id: z.string().min(1),
  filename: z.string().min(1),
  mediaType: z.enum(['image', 'video']),
  createdAt: z.string().nullable(),
  modifiedAt: z.string().nullable().optional(),
  width: z.number().nullable().optional(),
  height: z.number().nullable().optional(),
  durationSeconds: z.number().nullable().optional(),
  favorite: z.boolean(),
  hidden: z.boolean(),
  albumIds: z.array(z.string()),
  albumNames: z.array(z.string()),
  keywords: z.array(z.string()).optional(),
  location: LocationSchema.nullable().optional(),
  isCloudShared: z.boolean().optional(),
});

const ListAlbumsResultSchema = z.object({
  total: z.number().int().nonnegative(),
  albums: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      isSmart: z.boolean(),
      assetCount: z.number().int().nonnegative(),
    })
  ),
});

const SearchAssetsResultSchema = z.object({
  total: z.number().int().nonnegative(),
  items: z.array(RichAssetSchema),
});

const GetAssetResultSchema = z.object({
  item: RichAssetSchema,
});

const ExportAssetsScriptResultSchema = z.object({
  destinationPath: z.string().min(1),
  exported: z.array(
    z.object({
      assetId: z.string(),
      filePath: z.string(),
    })
  ),
  failed: z.array(
    z.object({
      assetId: z.string(),
      reason: z.string(),
      detail: z.string().optional(),
    })
  ),
});

type ListAlbumsParams = z.infer<typeof ListAlbumsSchema>;
type SearchAssetsParams = z.infer<typeof SearchAssetsSchema>;
type GetAssetParams = z.infer<typeof GetAssetSchema>;
type ExportAssetsParams = z.infer<typeof ExportAssetsSchema>;
type ListAlbumsResult = z.infer<typeof ListAlbumsResultSchema>;
type SearchAssetsResult = z.infer<typeof SearchAssetsResultSchema>;
type GetAssetResult = z.infer<typeof GetAssetResultSchema>;
type ExportAssetsScriptResult = z.infer<typeof ExportAssetsScriptResultSchema>;

interface ExportPathInfo {
  root: string;
  destinationPath: string;
}

function asMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function isPathWithin(parentPath: string, childPath: string): boolean {
  const relative = path.relative(parentPath, childPath);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function isErrnoException(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && 'code' in error;
}

class PhotosMCPError extends MCPServerError {
  constructor(
    mcpCode: MCPErrorCode,
    photosCode: string,
    message: string,
    details?: Record<string, unknown>
  ) {
    super(mcpCode, message, {
      photosCode,
      ...(details ?? {}),
    });
    this.name = 'PhotosMCPError';
  }
}

export class PhotosServer extends BaseMCPServer {
  constructor(
    private readonly scriptRunner: PhotosScriptRunner = new OsaScriptPhotosRunner()
  ) {
    super('photos', '1.0.0', 'Search, inspect, and export assets from macOS Photos');
  }

  protected async onInitialize(): Promise<void> {
    this.logger.info('Photos server initialized', {
      platform: process.platform,
      hasExportRoot: Boolean(process.env.PHOTOS_EXPORT_ROOT),
    });
  }

  protected async onShutdown(): Promise<void> {
    this.logger.info('Photos server shut down');
  }

  protected async registerTools(): Promise<void> {
    this.registerTool(
      'photos_list_albums',
      'List albums in the local Photos library',
      ListAlbumsSchema,
      createToolHandler<ListAlbumsParams>(async (params) =>
        this.listAlbums(params)
      )
    );

    this.registerTool(
      'photos_search_assets',
      'Search Photos assets with text and metadata filters',
      SearchAssetsSchema,
      createToolHandler<SearchAssetsParams>(async (params) =>
        this.searchAssets(params)
      )
    );

    this.registerTool(
      'photos_get_asset',
      'Get detailed metadata for a single Photos asset',
      GetAssetSchema,
      createToolHandler<GetAssetParams>(async (params) => this.getAsset(params))
    );

    this.registerTool(
      'photos_export_assets',
      'Export selected Photos assets into a sandboxed destination root',
      ExportAssetsSchema,
      createToolHandler<ExportAssetsParams>(async (params) =>
        this.exportAssets(params)
      )
    );
  }

  private async listAlbums(params: ListAlbumsParams): Promise<ListAlbumsResult> {
    return this.runOperation('list_albums', params, ListAlbumsResultSchema);
  }

  private async searchAssets(
    params: SearchAssetsParams
  ): Promise<SearchAssetsResult> {
    return this.runOperation('search_assets', params, SearchAssetsResultSchema);
  }

  private async getAsset(params: GetAssetParams): Promise<GetAssetResult> {
    return this.runOperation('get_asset', params, GetAssetResultSchema);
  }

  private async exportAssets(params: ExportAssetsParams): Promise<{
    destinationRoot: string;
    destinationPath: string;
    exported: ExportAssetsScriptResult['exported'];
    failed: ExportAssetsScriptResult['failed'];
  }> {
    const exportPath = await this.resolveExportPath(params.destinationSubdir);
    const scriptResult = await this.runOperation(
      'export_assets',
      {
        assetIds: params.assetIds,
        destinationPath: exportPath.destinationPath,
        overwrite: params.overwrite,
        exportVariant: params.exportVariant,
      },
      ExportAssetsScriptResultSchema
    );

    return {
      destinationRoot: exportPath.root,
      destinationPath: exportPath.destinationPath,
      exported: scriptResult.exported,
      failed: scriptResult.failed,
    };
  }

  private async runOperation<T>(
    operation: PhotosOperation,
    args: Record<string, unknown>,
    schema: z.ZodType<T>
  ): Promise<T> {
    try {
      const raw = await this.scriptRunner.runOperation(operation, args);
      return schema.parse(raw);
    } catch (error) {
      this.throwMappedError(error);
    }
  }

  private throwMappedError(error: unknown): never {
    if (error instanceof PhotosMCPError) {
      throw error;
    }

    if (error instanceof z.ZodError) {
      throw new PhotosMCPError(
        MCPErrorCode.InternalError,
        'PHOTOS_SCRIPT_ERROR',
        'Photos script returned an invalid payload',
        { issues: error.errors }
      );
    }

    if (error instanceof PhotosScriptError) {
      const mappedCode = this.mapMcpCode(error.photosCode);
      throw new PhotosMCPError(mappedCode, error.photosCode, error.message, {
        ...(error.details ?? {}),
      });
    }

    throw new PhotosMCPError(
      MCPErrorCode.InternalError,
      'PHOTOS_INTERNAL_ERROR',
      asMessage(error)
    );
  }

  private mapMcpCode(photosCode: string): MCPErrorCode {
    switch (photosCode) {
      case 'PHOTOS_AUTOMATION_DENIED':
      case 'PHOTOS_EXPORT_PATH_DENIED':
      case 'PHOTOS_EXPORT_ROOT_REQUIRED':
        return MCPErrorCode.PermissionDenied;
      case 'PHOTOS_INVALID_FILTER':
        return MCPErrorCode.InvalidParams;
      case 'PHOTOS_NOT_FOUND':
      case 'PHOTOS_APP_UNAVAILABLE':
        return MCPErrorCode.ResourceNotFound;
      default:
        return MCPErrorCode.InternalError;
    }
  }

  private async resolveExportPath(destinationSubdir: string): Promise<ExportPathInfo> {
    const configuredRoot = process.env.PHOTOS_EXPORT_ROOT;
    if (!configuredRoot || configuredRoot.trim().length === 0) {
      throw new PhotosMCPError(
        MCPErrorCode.PermissionDenied,
        'PHOTOS_EXPORT_ROOT_REQUIRED',
        'PHOTOS_EXPORT_ROOT must be set before using photos_export_assets'
      );
    }

    const normalizedSubdir = destinationSubdir.replace(/\\/g, '/').trim();
    if (path.isAbsolute(normalizedSubdir)) {
      throw new PhotosMCPError(
        MCPErrorCode.PermissionDenied,
        'PHOTOS_EXPORT_PATH_DENIED',
        'destinationSubdir must be relative to PHOTOS_EXPORT_ROOT'
      );
    }

    const safeSubdir = normalizedSubdir.length > 0 ? normalizedSubdir : 'exports';
    const posixNormalized = path.posix.normalize(safeSubdir);
    if (posixNormalized === '..' || posixNormalized.startsWith('../')) {
      throw new PhotosMCPError(
        MCPErrorCode.PermissionDenied,
        'PHOTOS_EXPORT_PATH_DENIED',
        'destinationSubdir cannot traverse outside PHOTOS_EXPORT_ROOT'
      );
    }

    const resolvedRootPath = path.resolve(configuredRoot);
    await fs.mkdir(resolvedRootPath, { recursive: true });
    const realRootPath = await fs.realpath(resolvedRootPath);
    const pathSegments = posixNormalized
      .split('/')
      .filter((segment) => segment.length > 0 && segment !== '.');

    let currentPath = realRootPath;
    for (const segment of pathSegments) {
      const nextPath = path.join(currentPath, segment);
      try {
        const stat = await fs.lstat(nextPath);
        if (stat.isSymbolicLink()) {
          throw new PhotosMCPError(
            MCPErrorCode.PermissionDenied,
            'PHOTOS_EXPORT_PATH_DENIED',
            'destinationSubdir contains a symbolic link path segment'
          );
        }
        if (!stat.isDirectory()) {
          throw new PhotosMCPError(
            MCPErrorCode.PermissionDenied,
            'PHOTOS_EXPORT_PATH_DENIED',
            'destinationSubdir collides with a non-directory path'
          );
        }
      } catch (error) {
        if (isErrnoException(error) && error.code === 'ENOENT') {
          await fs.mkdir(nextPath);
        } else {
          throw error;
        }
      }
      currentPath = nextPath;
    }

    const realCandidatePath = await fs.realpath(currentPath);

    if (!isPathWithin(realRootPath, realCandidatePath)) {
      throw new PhotosMCPError(
        MCPErrorCode.PermissionDenied,
        'PHOTOS_EXPORT_PATH_DENIED',
        'destinationSubdir resolved outside PHOTOS_EXPORT_ROOT'
      );
    }

    return {
      root: realRootPath,
      destinationPath: realCandidatePath,
    };
  }
}
