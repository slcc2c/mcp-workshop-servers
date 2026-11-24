"""macOS Photos JXA script and osascript runner."""
# ruff: noqa: E501

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

PhotosOperation = Literal["list_albums", "search_assets", "get_asset", "export_assets"]

PHOTOS_JXA_SCRIPT = """
ObjC.import('Foundation');
ObjC.import('stdlib');

function buildResponse(ok, result, error) {
  return {
    ok: ok,
    result: result || null,
    error: error || null,
  };
}

function readOperation() {
  var operation = $.getenv('MCP_PHOTOS_OPERATION');
  if (!operation) {
    throw new Error('Missing MCP_PHOTOS_OPERATION');
  }
  return String(operation);
}

function readArgs() {
  var encoded = $.getenv('MCP_PHOTOS_ARGS_B64');
  if (!encoded) {
    return {};
  }

  var encodedString = String(encoded);
  var data = $.NSData.alloc.initWithBase64EncodedStringOptions($(encodedString), 0);
  if (!data) {
    throw new Error('Unable to decode MCP_PHOTOS_ARGS_B64');
  }

  var decoded = $.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding);
  if (!decoded) {
    throw new Error('Unable to decode MCP_PHOTOS_ARGS_B64 as UTF-8');
  }

  return JSON.parse(ObjC.unwrap(decoded));
}

function deepUnwrap(value) {
  if (value === null || value === undefined) {
    return value;
  }

  try {
    return ObjC.deepUnwrap(value);
  } catch (error) {}

  try {
    return ObjC.unwrap(value);
  } catch (error) {}

  return value;
}

function toArray(value) {
  if (value === null || value === undefined) {
    return [];
  }

  if (Array.isArray(value)) {
    return value;
  }

  try {
    if (typeof value === 'function') {
      return toArray(value());
    }
  } catch (error) {}

  try {
    return Array.from(value);
  } catch (error) {}

  var unwrapped = deepUnwrap(value);
  if (Array.isArray(unwrapped)) {
    return unwrapped;
  }

  return [value];
}

function callAny(target, names) {
  if (!target) {
    return null;
  }

  for (var i = 0; i < names.length; i += 1) {
    var name = names[i];
    try {
      if (typeof target[name] === 'function') {
        return target[name]();
      }
      if (target[name] !== undefined) {
        return target[name];
      }
    } catch (error) {}
  }

  return null;
}

function asString(value) {
  if (value === null || value === undefined) {
    return '';
  }

  var unwrapped = deepUnwrap(value);
  if (unwrapped === null || unwrapped === undefined) {
    return '';
  }

  return String(unwrapped);
}

function asBoolean(value) {
  if (value === null || value === undefined) {
    return false;
  }

  var unwrapped = deepUnwrap(value);
  if (typeof unwrapped === 'boolean') {
    return unwrapped;
  }
  if (typeof unwrapped === 'number') {
    return unwrapped !== 0;
  }
  if (typeof unwrapped === 'string') {
    var normalized = unwrapped.toLowerCase();
    return normalized === 'true' || normalized === 'yes' || normalized === '1';
  }
  return Boolean(unwrapped);
}

function asNumberOrNull(value) {
  if (value === null || value === undefined) {
    return null;
  }
  var unwrapped = deepUnwrap(value);
  if (typeof unwrapped === 'number') {
    return Number.isFinite(unwrapped) ? unwrapped : null;
  }
  var parsed = Number(unwrapped);
  return Number.isFinite(parsed) ? parsed : null;
}

function toIsoStringOrNull(value) {
  if (value === null || value === undefined) {
    return null;
  }
  var unwrapped = deepUnwrap(value);
  var date = unwrapped instanceof Date ? unwrapped : new Date(unwrapped);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toISOString();
}

function normalizeLimit(limit, fallbackValue) {
  var parsed = Number(limit);
  if (!Number.isFinite(parsed)) {
    return fallbackValue;
  }
  if (parsed < 1) {
    return fallbackValue;
  }
  if (parsed > 500) {
    return 500;
  }
  return Math.floor(parsed);
}

function normalizeOffset(offset, fallbackValue) {
  var parsed = Number(offset);
  if (!Number.isFinite(parsed)) {
    return fallbackValue;
  }
  if (parsed < 0) {
    return fallbackValue;
  }
  return Math.floor(parsed);
}

function inferMediaType(filename, rawMediaType) {
  var loweredRaw = asString(rawMediaType).toLowerCase();
  if (loweredRaw.indexOf('video') >= 0 || loweredRaw.indexOf('movie') >= 0) {
    return 'video';
  }
  if (loweredRaw.indexOf('image') >= 0 || loweredRaw.indexOf('photo') >= 0) {
    return 'image';
  }

  var loweredFilename = asString(filename).toLowerCase();
  if (
    loweredFilename.endsWith('.mov') ||
    loweredFilename.endsWith('.mp4') ||
    loweredFilename.endsWith('.m4v') ||
    loweredFilename.endsWith('.avi') ||
    loweredFilename.endsWith('.mkv') ||
    loweredFilename.endsWith('.hevc')
  ) {
    return 'video';
  }

  return 'image';
}

function makeAlbumRecord(album, isSmart) {
  var albumName = asString(callAny(album, ['name']));
  var albumId =
    asString(callAny(album, ['id', 'localIdentifier', 'uuid'])) ||
    'album::' + albumName;
  var albumItems = toArray(callAny(album, ['mediaItems', 'assets']));

  return {
    id: albumId,
    name: albumName,
    isSmart: Boolean(isSmart),
    assetCount: albumItems.length,
    _raw: album,
  };
}

function collectAlbums(app, includeSmart) {
  var albums = [];
  var seen = {};

  var regularAlbums = toArray(callAny(app, ['albums']));
  for (var i = 0; i < regularAlbums.length; i += 1) {
    var record = makeAlbumRecord(regularAlbums[i], false);
    if (!record.id || seen[record.id]) {
      continue;
    }
    seen[record.id] = true;
    albums.push(record);
  }

  if (includeSmart) {
    var smartAlbums = toArray(callAny(app, ['smartAlbums']));
    for (var j = 0; j < smartAlbums.length; j += 1) {
      var smartRecord = makeAlbumRecord(smartAlbums[j], true);
      if (!smartRecord.id || seen[smartRecord.id]) {
        continue;
      }
      seen[smartRecord.id] = true;
      albums.push(smartRecord);
    }
  }

  return albums;
}

function buildMembershipMap(albumRecords) {
  var membership = {};

  for (var i = 0; i < albumRecords.length; i += 1) {
    var albumRecord = albumRecords[i];
    var items = toArray(callAny(albumRecord._raw, ['mediaItems', 'assets']));

    for (var j = 0; j < items.length; j += 1) {
      var item = items[j];
      var assetId =
        asString(callAny(item, ['id', 'localIdentifier', 'uuid'])) || null;
      if (!assetId) {
        continue;
      }

      if (!membership[assetId]) {
        membership[assetId] = {
          albumIds: [],
          albumNames: [],
        };
      }

      if (membership[assetId].albumIds.indexOf(albumRecord.id) === -1) {
        membership[assetId].albumIds.push(albumRecord.id);
      }
      if (membership[assetId].albumNames.indexOf(albumRecord.name) === -1) {
        membership[assetId].albumNames.push(albumRecord.name);
      }
    }
  }

  return membership;
}

function parseLocation(rawLocation) {
  if (!rawLocation) {
    return null;
  }

  var latitude = asNumberOrNull(callAny(rawLocation, ['latitude']));
  var longitude = asNumberOrNull(callAny(rawLocation, ['longitude']));

  if (latitude === null || longitude === null) {
    return null;
  }

  return {
    latitude: latitude,
    longitude: longitude,
  };
}

function toStringArray(value) {
  var values = toArray(value);
  var out = [];
  for (var i = 0; i < values.length; i += 1) {
    var text = asString(values[i]);
    if (text) {
      out.push(text);
    }
  }
  return out;
}

function makeAssetRecord(item, membershipMap) {
  var assetId =
    asString(callAny(item, ['id', 'localIdentifier', 'uuid'])) || null;

  if (!assetId) {
    return null;
  }

  var filename =
    asString(callAny(item, ['filename', 'name', 'title'])) ||
    assetId + '.jpg';
  var rawMediaType = callAny(item, ['mediaType', 'kind']);
  var mediaType = inferMediaType(filename, rawMediaType);
  var createdAt = toIsoStringOrNull(callAny(item, ['date', 'creationDate']));
  var modifiedAt = toIsoStringOrNull(
    callAny(item, ['modificationDate', 'dateModified'])
  );
  var width = asNumberOrNull(callAny(item, ['width', 'pixelWidth']));
  var height = asNumberOrNull(callAny(item, ['height', 'pixelHeight']));
  var durationSeconds = asNumberOrNull(
    callAny(item, ['duration', 'durationSeconds'])
  );
  var favorite = asBoolean(callAny(item, ['favorite', 'isFavorite']));
  var hidden = asBoolean(callAny(item, ['hidden', 'isHidden']));
  var keywords = toStringArray(callAny(item, ['keywords']));
  var location = parseLocation(callAny(item, ['location']));
  var isCloudShared = asBoolean(
    callAny(item, ['cloudShared', 'isCloudShared', 'shared'])
  );

  var membership = membershipMap[assetId] || { albumIds: [], albumNames: [] };

  return {
    id: assetId,
    filename: filename,
    mediaType: mediaType,
    createdAt: createdAt,
    modifiedAt: modifiedAt,
    width: width,
    height: height,
    durationSeconds: durationSeconds,
    favorite: favorite,
    hidden: hidden,
    albumIds: membership.albumIds,
    albumNames: membership.albumNames,
    keywords: keywords,
    location: location,
    isCloudShared: isCloudShared,
  };
}

function normalizeQuery(value) {
  var query = asString(value).trim().toLowerCase();
  return query;
}

function dateToEpoch(value) {
  if (!value) {
    return null;
  }
  var date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.getTime();
}

function filterAssets(assets, args) {
  var query = normalizeQuery(args.query);
  var dateFromEpoch = dateToEpoch(args.dateFrom);
  var dateToEpochValue = dateToEpoch(args.dateTo);
  var mediaType = asString(args.mediaType || 'any').toLowerCase();
  var hasFavoriteFilter = typeof args.isFavorite === 'boolean';
  var hasHiddenFilter = typeof args.isHidden === 'boolean';
  var albumIdFilter = asString(args.albumId);

  var filtered = [];

  for (var i = 0; i < assets.length; i += 1) {
    var asset = assets[i];

    if (mediaType && mediaType !== 'any' && asset.mediaType !== mediaType) {
      continue;
    }

    if (hasFavoriteFilter && asset.favorite !== args.isFavorite) {
      continue;
    }

    if (hasHiddenFilter && asset.hidden !== args.isHidden) {
      continue;
    }

    if (albumIdFilter && asset.albumIds.indexOf(albumIdFilter) === -1) {
      continue;
    }

    var createdEpoch = dateToEpoch(asset.createdAt);
    if (dateFromEpoch !== null && (createdEpoch === null || createdEpoch < dateFromEpoch)) {
      continue;
    }
    if (dateToEpochValue !== null && (createdEpoch === null || createdEpoch > dateToEpochValue)) {
      continue;
    }

    if (query) {
      var haystackParts = [
        asString(asset.filename).toLowerCase(),
        asset.albumNames.join(' ').toLowerCase(),
        (asset.keywords || []).join(' ').toLowerCase(),
      ];
      var haystack = haystackParts.join(' ');
      if (haystack.indexOf(query) === -1) {
        continue;
      }
    }

    filtered.push(asset);
  }

  return filtered;
}

function sortAssets(assets, sortOrder) {
  var direction = asString(sortOrder || 'created_desc');
  var sorted = assets.slice(0);

  sorted.sort(function(a, b) {
    var aEpoch = dateToEpoch(a.createdAt) || 0;
    var bEpoch = dateToEpoch(b.createdAt) || 0;

    if (direction === 'created_asc') {
      return aEpoch - bEpoch;
    }
    return bEpoch - aEpoch;
  });

  return sorted;
}

function paginate(items, limitValue, offsetValue) {
  var limit = normalizeLimit(limitValue, 100);
  var offset = normalizeOffset(offsetValue, 0);
  var total = items.length;
  var page = items.slice(offset, offset + limit);

  return {
    total: total,
    items: page,
  };
}

function collectAllMediaItems(app) {
  var directItems = toArray(callAny(app, ['mediaItems']));
  if (directItems.length > 0) {
    return directItems;
  }
  return [];
}

function performListAlbums(app, args) {
  var includeSmart = args.includeSmart !== false;
  var limit = normalizeLimit(args.limit, 200);
  var offset = normalizeOffset(args.offset, 0);

  var albumRecords = collectAlbums(app, includeSmart);
  var sliced = albumRecords.slice(offset, offset + limit);

  var albums = [];
  for (var i = 0; i < sliced.length; i += 1) {
    albums.push({
      id: sliced[i].id,
      name: sliced[i].name,
      isSmart: sliced[i].isSmart,
      assetCount: sliced[i].assetCount,
    });
  }

  return {
    total: albumRecords.length,
    albums: albums,
  };
}

function performSearchAssets(app, args) {
  var albumRecords = collectAlbums(app, true);
  var membershipMap = buildMembershipMap(albumRecords);
  var allItems = collectAllMediaItems(app);
  var assets = [];

  for (var i = 0; i < allItems.length; i += 1) {
    var mapped = makeAssetRecord(allItems[i], membershipMap);
    if (mapped) {
      assets.push(mapped);
    }
  }

  var filtered = filterAssets(assets, args || {});
  var sorted = sortAssets(filtered, args.sort);
  return paginate(sorted, args.limit, args.offset);
}

function performGetAsset(app, args) {
  var assetId = asString(args.assetId).trim();
  if (!assetId) {
    throw new Error('assetId is required');
  }

  var albumRecords = collectAlbums(app, true);
  var membershipMap = buildMembershipMap(albumRecords);
  var allItems = collectAllMediaItems(app);

  for (var i = 0; i < allItems.length; i += 1) {
    var mapped = makeAssetRecord(allItems[i], membershipMap);
    if (mapped && mapped.id === assetId) {
      return { item: mapped };
    }
  }

  return buildResponse(false, null, {
    code: 'PHOTOS_NOT_FOUND',
    message: 'Asset not found: ' + assetId,
    details: { assetId: assetId },
  });
}

function directoryFileList(directoryPath) {
  var manager = $.NSFileManager.defaultManager;
  var errorRef = Ref();
  var list = manager.contentsOfDirectoryAtPathError($(directoryPath), errorRef);
  if (!list) {
    return [];
  }
  var unwrapped = deepUnwrap(list);
  return Array.isArray(unwrapped) ? unwrapped : [];
}

function fileExists(filePath) {
  var manager = $.NSFileManager.defaultManager;
  return Boolean(manager.fileExistsAtPath($(filePath)));
}

function detectAvailabilityReason(message) {
  var lowered = asString(message).toLowerCase();
  if (
    lowered.indexOf('icloud') >= 0 ||
    lowered.indexOf('not available') >= 0 ||
    lowered.indexOf('cannot be accessed') >= 0
  ) {
    return 'not_local_or_unavailable';
  }
  return 'export_failed';
}

function attemptExport(app, item, destinationPath, exportVariant) {
  var destination = Path(destinationPath);
  var usingValue = exportVariant === 'original' ? 'originals' : 'current';

  try {
    app.export([item], { to: destination, using: usingValue });
    return null;
  } catch (firstError) {}

  try {
    app.export(item, { to: destination, using: usingValue });
    return null;
  } catch (secondError) {}

  try {
    app.export([item], { to: destination });
    return null;
  } catch (thirdError) {
    return asString(thirdError);
  }
}

function performExportAssets(app, args) {
  var assetIds = Array.isArray(args.assetIds) ? args.assetIds : [];
  var destinationPath = asString(args.destinationPath);
  var overwrite = args.overwrite === true;
  var exportVariant = asString(args.exportVariant || 'current');

  if (!destinationPath) {
    throw new Error('destinationPath is required');
  }

  var albumRecords = collectAlbums(app, true);
  var membershipMap = buildMembershipMap(albumRecords);
  var allItems = collectAllMediaItems(app);
  var itemById = {};

  for (var i = 0; i < allItems.length; i += 1) {
    var item = allItems[i];
    var itemId = asString(callAny(item, ['id', 'localIdentifier', 'uuid']));
    if (itemId) {
      itemById[itemId] = item;
    }
  }

  var exported = [];
  var failed = [];

  for (var j = 0; j < assetIds.length; j += 1) {
    var assetId = asString(assetIds[j]);
    var targetItem = itemById[assetId];

    if (!targetItem) {
      failed.push({
        assetId: assetId,
        reason: 'not_found',
        detail: 'Asset not found in Photos library',
      });
      continue;
    }

    var mapped = makeAssetRecord(targetItem, membershipMap);
    var fallbackFilename = mapped ? mapped.filename : assetId + '.jpg';
    var fallbackPath = destinationPath + '/' + fallbackFilename;

    if (!overwrite && fileExists(fallbackPath)) {
      failed.push({
        assetId: assetId,
        reason: 'already_exists',
        detail: 'Target file already exists',
      });
      continue;
    }

    var beforeFiles = directoryFileList(destinationPath);
    var beforeSet = {};
    for (var b = 0; b < beforeFiles.length; b += 1) {
      beforeSet[beforeFiles[b]] = true;
    }

    var exportError = attemptExport(app, targetItem, destinationPath, exportVariant);
    if (exportError) {
      failed.push({
        assetId: assetId,
        reason: detectAvailabilityReason(exportError),
        detail: exportError,
      });
      continue;
    }

    var afterFiles = directoryFileList(destinationPath);
    var detectedPath = null;
    for (var a = 0; a < afterFiles.length; a += 1) {
      var fileName = afterFiles[a];
      if (!beforeSet[fileName]) {
        detectedPath = destinationPath + '/' + fileName;
        break;
      }
    }

    if (!detectedPath) {
      detectedPath = fallbackPath;
    }

    exported.push({
      assetId: assetId,
      filePath: detectedPath,
    });
  }

  return {
    destinationPath: destinationPath,
    exported: exported,
    failed: failed,
  };
}

function execute(operation, args) {
  var photos = connectPhotosApplication();

  if (operation === 'list_albums') {
    return performListAlbums(photos, args);
  }

  if (operation === 'search_assets') {
    return performSearchAssets(photos, args);
  }

  if (operation === 'get_asset') {
    return performGetAsset(photos, args);
  }

  if (operation === 'export_assets') {
    return performExportAssets(photos, args);
  }

  throw new Error('Unknown operation: ' + operation);
}

function inferErrorCode(message) {
  var lowered = asString(message).toLowerCase();
  if (lowered.indexOf('not authorized') >= 0 || lowered.indexOf('not permitted') >= 0) {
    return 'PHOTOS_AUTOMATION_DENIED';
  }
  if (lowered.indexOf('application can\'t be found') >= 0 || lowered.indexOf('photos') >= 0 && lowered.indexOf('not running') >= 0) {
    return 'PHOTOS_APP_UNAVAILABLE';
  }
  return 'PHOTOS_SCRIPT_ERROR';
}

function connectPhotosApplication() {
  var candidates = [
    '/System/Applications/Photos.app',
    'com.apple.Photos',
    'Photos',
  ];
  var lastError = null;

  for (var i = 0; i < candidates.length; i += 1) {
    try {
      var app = Application(candidates[i]);
      app.includeStandardAdditions = true;
      var resolvedName = app.name();
      if (resolvedName !== 'Photos') {
        throw new Error('Resolved to ' + resolvedName + ', not Photos');
      }
      return app;
    } catch (error) {
      lastError = error;
    }
  }

  if (lastError) {
    throw lastError;
  }
  throw new Error('Photos application is unavailable');
}

function main() {
  try {
    var operation = readOperation();
    var args = readArgs();
    var result = execute(operation, args);

    if (result && result.ok === false && result.error) {
      return result;
    }

    return buildResponse(true, result, null);
  } catch (error) {
    var message = asString(error && error.message ? error.message : error);
    return buildResponse(false, null, {
      code: inferErrorCode(message),
      message: message || 'Photos script failed',
    });
  }
}

JSON.stringify(main());
"""


class PhotosScriptRunner(Protocol):
    async def run_operation(
        self,
        operation: PhotosOperation,
        args: dict[str, Any],
    ) -> Any: ...


@dataclass(frozen=True)
class OsaExecResult:
    stdout: str
    stderr: str


OsaExecutor = Callable[[list[str], dict[str, str], float], Awaitable[OsaExecResult]]


class PhotosScriptError(RuntimeError):
    """Error raised when osascript execution or JXA payload fails."""

    def __init__(
        self,
        photos_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.photos_code = photos_code
        self.details = details or {}
        super().__init__(message)


def _infer_error_code(message: str) -> str:
    lowered = message.lower()
    if (
        "not authorized" in lowered
        or "not permitted" in lowered
        or "apple events" in lowered
    ):
        return "PHOTOS_AUTOMATION_DENIED"
    if (
        "can’t be found" in lowered
        or "can't be found" in lowered
        or "application isn’t running" in lowered
        or "application isn't running" in lowered
        or 'unable to locate application "photos"' in lowered
    ):
        return "PHOTOS_APP_UNAVAILABLE"
    if "timeout" in lowered or "timed out" in lowered:
        return "PHOTOS_SCRIPT_TIMEOUT"
    return "PHOTOS_SCRIPT_ERROR"


def _parse_script_response(stdout: str) -> dict[str, Any]:
    trimmed = stdout.strip()
    if not trimmed:
        raise PhotosScriptError(
            "PHOTOS_SCRIPT_ERROR",
            "Photos script returned empty output",
            {"stdout": stdout},
        )

    lines = [line.strip() for line in trimmed.splitlines() if line.strip()]
    payload_text = lines[-1] if lines else trimmed

    try:
        parsed = json.loads(payload_text)
    except Exception as exc:
        raise PhotosScriptError(
            "PHOTOS_SCRIPT_ERROR",
            "Photos script returned invalid JSON",
            {"stdout": payload_text, "parseError": str(exc)},
        ) from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("ok"), bool):
        raise PhotosScriptError(
            "PHOTOS_SCRIPT_ERROR",
            "Photos script returned unexpected payload",
            {"stdout": payload_text},
        )
    return parsed


async def _default_executor(
    args: list[str],
    env: dict[str, str],
    timeout_seconds: float,
) -> OsaExecResult:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            env=env,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    try:
        proc = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired as exc:
        raise PhotosScriptError(
            "PHOTOS_SCRIPT_TIMEOUT",
            f"Photos osascript timed out after {timeout_seconds}s",
        ) from exc

    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"osascript exited {proc.returncode}"
        raise PhotosScriptError(
            _infer_error_code(msg),
            msg,
            {"exitCode": proc.returncode, "stderr": proc.stderr, "stdout": proc.stdout},
        )
    return OsaExecResult(stdout=proc.stdout, stderr=proc.stderr)


class OsaScriptPhotosRunner:
    """Executes macOS Photos operations via osascript JXA."""

    def __init__(
        self,
        executor: OsaExecutor | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self._executor = executor or _default_executor
        self._timeout_seconds = timeout_seconds

    async def run_operation(
        self,
        operation: PhotosOperation,
        args: dict[str, Any],
    ) -> Any:
        encoded = base64.b64encode(json.dumps(args).encode("utf-8")).decode("ascii")
        env = dict(os.environ)
        env["MCP_PHOTOS_OPERATION"] = operation
        env["MCP_PHOTOS_ARGS_B64"] = encoded

        try:
            res = await self._executor(
                ["osascript", "-l", "JavaScript", "-e", PHOTOS_JXA_SCRIPT],
                env,
                self._timeout_seconds,
            )
            parsed = _parse_script_response(res.stdout)
            if parsed.get("ok"):
                return parsed.get("result")

            raw_err = parsed.get("error")
            err: dict[str, Any] = raw_err if isinstance(raw_err, dict) else {}
            raw_code = err.get("code")
            code = raw_code if isinstance(raw_code, str) else "PHOTOS_SCRIPT_ERROR"
            raw_msg = err.get("message")
            msg = raw_msg if isinstance(raw_msg, str) else "Photos script failed"
            raw_details = err.get("details")
            details: dict[str, Any] = (
                dict(raw_details) if isinstance(raw_details, dict) else {}
            )
            details["stderr"] = res.stderr
            raise PhotosScriptError(code, msg, details)
        except PhotosScriptError:
            raise
        except Exception as exc:
            msg = str(exc) or "Photos script failed"
            raise PhotosScriptError(_infer_error_code(msg), msg, {"operation": operation}) from exc
