/**
 * XcodeBuildMCP Server
 * Provides comprehensive Xcode, Swift, and iOS/macOS development capabilities
 */

import { z } from 'zod';
import { spawn, ChildProcess } from 'child_process';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { ResourceNotFoundError } from '../../src/utils/errors';
import * as path from 'path';
import * as fs from 'fs/promises';

// Input schemas for Xcode project management
const DiscoverProjectsSchema = z.object({
  path: z.string().describe('Directory path to search for Xcode projects'),
  recursive: z.boolean().default(true).describe('Search recursively in subdirectories'),
});

const BuildProjectSchema = z.object({
  projectPath: z.string().describe('Path to .xcodeproj or .xcworkspace'),
  scheme: z.string().describe('Build scheme name'),
  configuration: z.enum(['Debug', 'Release']).default('Debug').describe('Build configuration'),
  destination: z.string().optional().describe('Build destination (e.g., "platform=iOS Simulator,name=iPhone 15")'),
  derivedDataPath: z.string().optional().describe('Custom derived data path'),
  clean: z.boolean().default(false).describe('Clean before building'),
  allowProvisioningUpdates: z.boolean().default(false).describe('Allow automatic provisioning updates'),
});

const ShowBuildSettingsSchema = z.object({
  projectPath: z.string().describe('Path to .xcodeproj or .xcworkspace'),
  scheme: z.string().optional().describe('Scheme name'),
  configuration: z.enum(['Debug', 'Release']).default('Debug').describe('Build configuration'),
});

const ListSchemesSchema = z.object({
  projectPath: z.string().describe('Path to .xcodeproj or .xcworkspace'),
});

const CleanProjectSchema = z.object({
  projectPath: z.string().describe('Path to .xcodeproj or .xcworkspace'),
  scheme: z.string().describe('Scheme to clean'),
  configuration: z.enum(['Debug', 'Release']).default('Debug').describe('Build configuration'),
  derivedDataPath: z.string().optional().describe('Custom derived data path'),
});

// Input schemas for Swift Package Manager
const BuildPackageSchema = z.object({
  packagePath: z.string().describe('Path to Swift package directory'),
  configuration: z.enum(['debug', 'release']).default('debug').describe('Build configuration'),
  product: z.string().optional().describe('Specific product to build'),
  platform: z.string().optional().describe('Target platform'),
});

const TestPackageSchema = z.object({
  packagePath: z.string().describe('Path to Swift package directory'),
  configuration: z.enum(['debug', 'release']).default('debug').describe('Build configuration'),
  filter: z.string().optional().describe('Test filter pattern'),
  parallel: z.boolean().default(true).describe('Run tests in parallel'),
});

const RunPackageExecutableSchema = z.object({
  packagePath: z.string().describe('Path to Swift package directory'),
  executable: z.string().describe('Executable name to run'),
  arguments: z.array(z.string()).default([]).describe('Arguments to pass to executable'),
  configuration: z.enum(['debug', 'release']).default('debug').describe('Build configuration'),
});

// Input schemas for simulator management
const ListSimulatorsSchema = z.object({
  runtime: z.string().optional().describe('Filter by runtime (e.g., "iOS 17.0")'),
  deviceType: z.string().optional().describe('Filter by device type (e.g., "iPhone 15")'),
  available: z.boolean().default(true).describe('Only show available simulators'),
});

const BootSimulatorSchema = z.object({
  simulatorId: z.string().describe('Simulator UUID or name'),
});

const InstallAppSchema = z.object({
  simulatorId: z.string().describe('Simulator UUID or name'),
  appPath: z.string().describe('Path to .app bundle'),
});

const LaunchAppSchema = z.object({
  simulatorId: z.string().describe('Simulator UUID or name'),
  bundleId: z.string().describe('App bundle identifier'),
  arguments: z.array(z.string()).default([]).describe('Launch arguments'),
  environment: z.record(z.string()).default({}).describe('Environment variables'),
});

const CaptureScreenshotSchema = z.object({
  simulatorId: z.string().describe('Simulator UUID or name'),
  outputPath: z.string().describe('Path to save screenshot'),
  type: z.enum(['png', 'jpeg', 'tiff']).default('png').describe('Screenshot format'),
});

// Input schemas for device management
const ListDevicesSchema = z.object({
  platform: z.enum(['iOS', 'tvOS', 'watchOS', 'all']).default('all').describe('Filter by platform'),
  connected: z.boolean().default(true).describe('Only show connected devices'),
});

const InstallAppOnDeviceSchema = z.object({
  deviceId: z.string().describe('Device UUID or name'),
  appPath: z.string().describe('Path to .app or .ipa file'),
});

const LaunchAppOnDeviceSchema = z.object({
  deviceId: z.string().describe('Device UUID or name'),
  bundleId: z.string().describe('App bundle identifier'),
  waitForDebugger: z.boolean().default(false).describe('Wait for debugger to attach'),
});

// Input schemas for utilities
const GetBundleIdSchema = z.object({
  appPath: z.string().describe('Path to .app bundle'),
});

const CreateProjectSchema = z.object({
  name: z.string().describe('Project name'),
  path: z.string().describe('Directory to create project in'),
  bundleId: z.string().describe('Bundle identifier'),
  platform: z.enum(['iOS', 'macOS', 'tvOS', 'watchOS']).default('iOS').describe('Target platform'),
  language: z.enum(['Swift', 'Objective-C']).default('Swift').describe('Programming language'),
  uiFramework: z.enum(['SwiftUI', 'UIKit', 'AppKit']).default('SwiftUI').describe('UI framework'),
  includeTests: z.boolean().default(true).describe('Include unit and UI tests'),
  includeGit: z.boolean().default(true).describe('Initialize git repository'),
});

export class XcodeBuildServer extends BaseMCPServer {
  private runningProcesses: Map<string, ChildProcess> = new Map();
  private xcodebuildPath: string = '/usr/bin/xcodebuild';
  private simctlPath: string = '/usr/bin/xcrun';

  constructor() {
    super('xcodebuild', '1.0.0', 'Xcode build and development tools integration');
  }

  protected async onInitialize(): Promise<void> {
    // Verify Xcode tools are available
    try {
      await this.executeCommand([this.xcodebuildPath, '-version']);
      this.logger.info('Xcode tools verified');
    } catch (error) {
      this.logger.error('Xcode tools not found', { error });
      throw new Error('Xcode Command Line Tools not installed. Run: xcode-select --install');
    }

    // Check if running on macOS
    if (process.platform !== 'darwin') {
      throw new Error('XcodeBuildMCP server requires macOS');
    }
  }

  protected async onShutdown(): Promise<void> {
    // Stop all running processes
    this.runningProcesses.forEach((process, id) => {
      this.logger.info('Stopping process', { id });
      process.kill();
    });
    this.runningProcesses.clear();
  }

  protected async registerTools(): Promise<void> {
    // Xcode Project Management Tools
    this.registerTool(
      'xcode_discover_projects',
      'Discover Xcode projects and workspaces in a directory',
      DiscoverProjectsSchema,
      createToolHandler(async (params: z.infer<typeof DiscoverProjectsSchema>) => {
        return this.discoverProjects(params);
      })
    );

    this.registerTool(
      'xcode_build_project',
      'Build an Xcode project or workspace',
      BuildProjectSchema,
      createToolHandler(async (params: z.infer<typeof BuildProjectSchema>) => {
        return this.buildProject(params);
      })
    );

    this.registerTool(
      'xcode_show_build_settings',
      'Show build settings for a project',
      ShowBuildSettingsSchema,
      createToolHandler(async (params: z.infer<typeof ShowBuildSettingsSchema>) => {
        return this.showBuildSettings(params);
      })
    );

    this.registerTool(
      'xcode_list_schemes',
      'List available schemes in a project',
      ListSchemesSchema,
      createToolHandler(async (params: z.infer<typeof ListSchemesSchema>) => {
        return this.listSchemes(params);
      })
    );

    this.registerTool(
      'xcode_clean_project',
      'Clean build artifacts for a project',
      CleanProjectSchema,
      createToolHandler(async (params: z.infer<typeof CleanProjectSchema>) => {
        return this.cleanProject(params);
      })
    );

    // Swift Package Manager Tools
    this.registerTool(
      'swift_build_package',
      'Build a Swift package',
      BuildPackageSchema,
      createToolHandler(async (params: z.infer<typeof BuildPackageSchema>) => {
        return this.buildSwiftPackage(params);
      })
    );

    this.registerTool(
      'swift_test_package',
      'Run tests for a Swift package',
      TestPackageSchema,
      createToolHandler(async (params: z.infer<typeof TestPackageSchema>) => {
        return this.testSwiftPackage(params);
      })
    );

    this.registerTool(
      'swift_run_executable',
      'Run an executable from a Swift package',
      RunPackageExecutableSchema,
      createToolHandler(async (params: z.infer<typeof RunPackageExecutableSchema>) => {
        return this.runSwiftExecutable(params);
      })
    );

    // Simulator Management Tools
    this.registerTool(
      'simulator_list',
      'List available iOS simulators',
      ListSimulatorsSchema,
      createToolHandler(async (params: z.infer<typeof ListSimulatorsSchema>) => {
        return this.listSimulators(params);
      })
    );

    this.registerTool(
      'simulator_boot',
      'Boot an iOS simulator',
      BootSimulatorSchema,
      createToolHandler(async (params: z.infer<typeof BootSimulatorSchema>) => {
        return this.bootSimulator(params);
      })
    );

    this.registerTool(
      'simulator_install_app',
      'Install an app on a simulator',
      InstallAppSchema,
      createToolHandler(async (params: z.infer<typeof InstallAppSchema>) => {
        return this.installAppOnSimulator(params);
      })
    );

    this.registerTool(
      'simulator_launch_app',
      'Launch an app on a simulator',
      LaunchAppSchema,
      createToolHandler(async (params: z.infer<typeof LaunchAppSchema>) => {
        return this.launchAppOnSimulator(params);
      })
    );

    this.registerTool(
      'simulator_screenshot',
      'Capture a screenshot from a simulator',
      CaptureScreenshotSchema,
      createToolHandler(async (params: z.infer<typeof CaptureScreenshotSchema>) => {
        return this.captureSimulatorScreenshot(params);
      })
    );

    // Device Management Tools
    this.registerTool(
      'device_list',
      'List connected Apple devices',
      ListDevicesSchema,
      createToolHandler(async (params: z.infer<typeof ListDevicesSchema>) => {
        return this.listDevices(params);
      })
    );

    this.registerTool(
      'device_install_app',
      'Install an app on a physical device',
      InstallAppOnDeviceSchema,
      createToolHandler(async (params: z.infer<typeof InstallAppOnDeviceSchema>) => {
        return this.installAppOnDevice(params);
      })
    );

    this.registerTool(
      'device_launch_app',
      'Launch an app on a physical device',
      LaunchAppOnDeviceSchema,
      createToolHandler(async (params: z.infer<typeof LaunchAppOnDeviceSchema>) => {
        return this.launchAppOnDevice(params);
      })
    );

    // Utility Tools
    this.registerTool(
      'app_get_bundle_id',
      'Extract bundle identifier from an app',
      GetBundleIdSchema,
      createToolHandler(async (params: z.infer<typeof GetBundleIdSchema>) => {
        return this.getBundleId(params);
      })
    );

    this.registerTool(
      'xcode_create_project',
      'Create a new Xcode project from template',
      CreateProjectSchema,
      createToolHandler(async (params: z.infer<typeof CreateProjectSchema>) => {
        return this.createProject(params);
      })
    );

    this.registerTool(
      'process_list',
      'List running processes started by this server',
      z.object({}),
      createToolHandler(async () => {
        return this.listRunningProcesses();
      })
    );

    this.registerTool(
      'process_stop',
      'Stop a running process',
      z.object({
        processId: z.string().describe('Process ID to stop'),
      }),
      createToolHandler(async ({ processId }: { processId: string }) => {
        return this.stopProcess(processId);
      })
    );
  }

  // Implementation methods

  private async executeCommand(args: string[], options: any = {}): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const child = spawn(args[0], args.slice(1), {
        ...options,
        env: { ...process.env, ...options.env },
      });

      let stdout = '';
      let stderr = '';

      child.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (code === 0) {
          resolve({ stdout, stderr });
        } else {
          reject(new Error(`Command failed with code ${code}: ${stderr}`));
        }
      });

      child.on('error', (error) => {
        reject(error);
      });
    });
  }

  private async discoverProjects(params: z.infer<typeof DiscoverProjectsSchema>) {
    const projects: Array<{ path: string; type: string; name: string }> = [];
    
    async function searchDirectory(dir: string, recursive: boolean) {
      try {
        const entries = await fs.readdir(dir, { withFileTypes: true });
        
        for (const entry of entries) {
          const fullPath = path.join(dir, entry.name);
          
          if (entry.isDirectory()) {
            if (entry.name.endsWith('.xcworkspace')) {
              projects.push({
                path: fullPath,
                type: 'workspace',
                name: entry.name.replace('.xcworkspace', ''),
              });
            } else if (entry.name.endsWith('.xcodeproj')) {
              projects.push({
                path: fullPath,
                type: 'project',
                name: entry.name.replace('.xcodeproj', ''),
              });
            } else if (recursive && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
              await searchDirectory(fullPath, recursive);
            }
          }
        }
      } catch (error) {
        // Ignore permission errors
      }
    }

    await searchDirectory(params.path, params.recursive);
    
    return {
      projects,
      count: projects.length,
      searchPath: params.path,
    };
  }

  private async buildProject(params: z.infer<typeof BuildProjectSchema>) {
    const args = [this.xcodebuildPath];
    
    // Determine project type
    if (params.projectPath.endsWith('.xcworkspace')) {
      args.push('-workspace', params.projectPath);
    } else {
      args.push('-project', params.projectPath);
    }
    
    args.push('-scheme', params.scheme);
    args.push('-configuration', params.configuration);
    
    if (params.destination) {
      args.push('-destination', params.destination);
    }
    
    if (params.derivedDataPath) {
      args.push('-derivedDataPath', params.derivedDataPath);
    }
    
    if (params.allowProvisioningUpdates) {
      args.push('-allowProvisioningUpdates');
    }
    
    if (params.clean) {
      args.push('clean');
    }
    
    args.push('build');
    
    try {
      const startTime = Date.now();
      const result = await this.executeCommand(args);
      const duration = Date.now() - startTime;
      
      // Parse build results
      const succeeded = result.stdout.includes('BUILD SUCCEEDED');
      const warnings = (result.stdout.match(/warning:/g) || []).length;
      const errors = (result.stdout.match(/error:/g) || []).length;
      
      return {
        success: succeeded,
        duration: `${(duration / 1000).toFixed(2)}s`,
        warnings,
        errors,
        output: result.stdout,
        project: params.projectPath,
        scheme: params.scheme,
        configuration: params.configuration,
      };
    } catch (error: any) {
      // Extract error details from build output
      const errorMatch = error.message.match(/error: (.+)/);
      const errorDetail = errorMatch ? errorMatch[1] : error.message;
      
      throw new Error(`Build failed: ${errorDetail}`);
    }
  }

  private async showBuildSettings(params: z.infer<typeof ShowBuildSettingsSchema>) {
    const args = [this.xcodebuildPath];
    
    if (params.projectPath.endsWith('.xcworkspace')) {
      args.push('-workspace', params.projectPath);
    } else {
      args.push('-project', params.projectPath);
    }
    
    if (params.scheme) {
      args.push('-scheme', params.scheme);
    }
    
    args.push('-configuration', params.configuration);
    args.push('-showBuildSettings');
    
    const result = await this.executeCommand(args);
    
    // Parse build settings
    const settings: Record<string, string> = {};
    const lines = result.stdout.split('\n');
    
    for (const line of lines) {
      const match = line.match(/^\s*(\w+)\s*=\s*(.+)$/);
      if (match) {
        settings[match[1]] = match[2].trim();
      }
    }
    
    return {
      settings,
      project: params.projectPath,
      configuration: params.configuration,
      scheme: params.scheme,
    };
  }

  private async listSchemes(params: z.infer<typeof ListSchemesSchema>) {
    const args = [this.xcodebuildPath];
    
    if (params.projectPath.endsWith('.xcworkspace')) {
      args.push('-workspace', params.projectPath);
    } else {
      args.push('-project', params.projectPath);
    }
    
    args.push('-list');
    
    const result = await this.executeCommand(args);
    
    // Parse schemes from output
    const schemes: string[] = [];
    const lines = result.stdout.split('\n');
    let inSchemesSection = false;
    
    for (const line of lines) {
      if (line.includes('Schemes:')) {
        inSchemesSection = true;
        continue;
      }
      
      if (inSchemesSection && line.trim()) {
        if (!line.startsWith(' ')) {
          break;
        }
        schemes.push(line.trim());
      }
    }
    
    return {
      schemes,
      project: params.projectPath,
      count: schemes.length,
    };
  }

  private async cleanProject(params: z.infer<typeof CleanProjectSchema>) {
    const args = [this.xcodebuildPath];
    
    if (params.projectPath.endsWith('.xcworkspace')) {
      args.push('-workspace', params.projectPath);
    } else {
      args.push('-project', params.projectPath);
    }
    
    args.push('-scheme', params.scheme);
    args.push('-configuration', params.configuration);
    
    if (params.derivedDataPath) {
      args.push('-derivedDataPath', params.derivedDataPath);
    }
    
    args.push('clean');
    
    const result = await this.executeCommand(args);
    const succeeded = result.stdout.includes('CLEAN SUCCEEDED');
    
    return {
      success: succeeded,
      project: params.projectPath,
      scheme: params.scheme,
      configuration: params.configuration,
    };
  }

  private async buildSwiftPackage(params: z.infer<typeof BuildPackageSchema>) {
    const args = ['swift', 'build'];
    
    args.push('-c', params.configuration);
    
    if (params.product) {
      args.push('--product', params.product);
    }
    
    if (params.platform) {
      args.push('--platform', params.platform);
    }
    
    const result = await this.executeCommand(args, {
      cwd: params.packagePath,
    });
    
    return {
      success: true,
      output: result.stdout,
      packagePath: params.packagePath,
      configuration: params.configuration,
    };
  }

  private async testSwiftPackage(params: z.infer<typeof TestPackageSchema>) {
    const args = ['swift', 'test'];
    
    args.push('-c', params.configuration);
    
    if (params.filter) {
      args.push('--filter', params.filter);
    }
    
    if (params.parallel) {
      args.push('--parallel');
    }
    
    try {
      const result = await this.executeCommand(args, {
        cwd: params.packagePath,
      });
      
      // Parse test results
      const testsMatch = result.stdout.match(/Test Suite .+ passed.+\n.+ \((\d+)\) tests?.+in ([\d.]+) seconds/);
      const testCount = testsMatch ? parseInt(testsMatch[1]) : 0;
      const duration = testsMatch ? testsMatch[2] : 'unknown';
      
      return {
        success: true,
        testCount,
        duration: `${duration}s`,
        output: result.stdout,
        packagePath: params.packagePath,
      };
    } catch (error: any) {
      const failureMatch = error.message.match(/(\d+) tests? failed/);
      const failedCount = failureMatch ? parseInt(failureMatch[1]) : 'unknown';
      
      throw new Error(`Tests failed: ${failedCount} test(s) failed`);
    }
  }

  private async runSwiftExecutable(params: z.infer<typeof RunPackageExecutableSchema>) {
    const processId = `swift-${Date.now()}`;
    const args = ['swift', 'run', params.executable];
    
    args.push('-c', params.configuration);
    args.push(...params.arguments);
    
    const child = spawn(args[0], args.slice(1), {
      cwd: params.packagePath,
    });
    
    this.runningProcesses.set(processId, child);
    
    // Capture initial output
    let output = '';
    const captureOutput = (data: Buffer) => {
      output += data.toString();
    };
    
    child.stdout?.on('data', captureOutput);
    child.stderr?.on('data', captureOutput);
    
    // Give it a moment to start
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    child.stdout?.off('data', captureOutput);
    child.stderr?.off('data', captureOutput);
    
    return {
      processId,
      executable: params.executable,
      arguments: params.arguments,
      status: 'running',
      output,
    };
  }

  private async listSimulators(params: z.infer<typeof ListSimulatorsSchema>) {
    const args = [this.simctlPath, 'simctl', 'list', 'devices', '--json'];
    
    const result = await this.executeCommand(args);
    const data = JSON.parse(result.stdout);
    
    const simulators: Array<{
      udid: string;
      name: string;
      state: string;
      runtime: string;
      deviceType: string;
    }> = [];
    
    for (const [runtime, devices] of Object.entries(data.devices)) {
      if (params.runtime && !runtime.includes(params.runtime)) {
        continue;
      }
      
      for (const device of devices as any[]) {
        if (params.available && device.state !== 'Booted' && device.state !== 'Shutdown') {
          continue;
        }
        
        if (params.deviceType && !device.name.includes(params.deviceType)) {
          continue;
        }
        
        simulators.push({
          udid: device.udid,
          name: device.name,
          state: device.state,
          runtime: runtime.replace('com.apple.CoreSimulator.SimRuntime.', ''),
          deviceType: device.deviceTypeIdentifier.split('.').pop() || '',
        });
      }
    }
    
    return {
      simulators,
      count: simulators.length,
    };
  }

  private async bootSimulator(params: z.infer<typeof BootSimulatorSchema>) {
    const args = [this.simctlPath, 'simctl', 'boot', params.simulatorId];
    
    try {
      await this.executeCommand(args);
      
      // Open Simulator app
      await this.executeCommand(['open', '-a', 'Simulator']);
      
      return {
        simulatorId: params.simulatorId,
        booted: true,
      };
    } catch (error: any) {
      if (error.message.includes('Unable to boot device in current state: Booted')) {
        return {
          simulatorId: params.simulatorId,
          booted: true,
          message: 'Simulator already booted',
        };
      }
      throw error;
    }
  }

  private async installAppOnSimulator(params: z.infer<typeof InstallAppSchema>) {
    const args = [this.simctlPath, 'simctl', 'install', params.simulatorId, params.appPath];
    
    await this.executeCommand(args);
    
    return {
      simulatorId: params.simulatorId,
      appPath: params.appPath,
      installed: true,
    };
  }

  private async launchAppOnSimulator(params: z.infer<typeof LaunchAppSchema>) {
    const args = [this.simctlPath, 'simctl', 'launch'];
    
    // Add environment variables
    for (const [key, value] of Object.entries(params.environment)) {
      args.push('-e', `${key}=${value}`);
    }
    
    args.push(params.simulatorId, params.bundleId);
    
    // Add launch arguments
    args.push(...params.arguments);
    
    const result = await this.executeCommand(args);
    
    // Extract PID from output
    const pid = result.stdout.trim();
    
    return {
      simulatorId: params.simulatorId,
      bundleId: params.bundleId,
      pid,
      launched: true,
    };
  }

  private async captureSimulatorScreenshot(params: z.infer<typeof CaptureScreenshotSchema>) {
    const args = [
      this.simctlPath,
      'simctl',
      'io',
      params.simulatorId,
      'screenshot',
      '--type',
      params.type,
      params.outputPath,
    ];
    
    await this.executeCommand(args);
    
    return {
      simulatorId: params.simulatorId,
      outputPath: params.outputPath,
      type: params.type,
      captured: true,
    };
  }

  private async listDevices(params: z.infer<typeof ListDevicesSchema>) {
    const args = [this.simctlPath, 'devicectl', 'list', 'devices', '--json'];
    
    try {
      const result = await this.executeCommand(args);
      const data = JSON.parse(result.stdout);
      
      const devices = data.result.devices.filter((device: any) => {
        if (params.platform !== 'all' && device.platform !== params.platform) {
          return false;
        }
        
        if (params.connected && device.connectionType === 'none') {
          return false;
        }
        
        return true;
      });
      
      return {
        devices: devices.map((device: any) => ({
          identifier: device.identifier,
          name: device.name,
          platform: device.platform,
          osVersion: device.osVersion,
          connectionType: device.connectionType,
          modelName: device.modelName,
        })),
        count: devices.length,
      };
    } catch (error) {
      // Fallback to older method if devicectl is not available
      const result = await this.executeCommand(['instruments', '-s', 'devices']);
      
      const devices: Array<{ name: string; identifier: string; platform: string }> = [];
      const lines = result.stdout.split('\n');
      
      for (const line of lines) {
        const match = line.match(/(.+) \[([A-F0-9-]+)\]/);
        if (match && !line.includes('Simulator')) {
          devices.push({
            name: match[1].trim(),
            identifier: match[2],
            platform: 'iOS', // Assume iOS for older method
          });
        }
      }
      
      return {
        devices,
        count: devices.length,
      };
    }
  }

  private async installAppOnDevice(params: z.infer<typeof InstallAppOnDeviceSchema>) {
    const args = [
      this.simctlPath,
      'devicectl',
      'device',
      'install',
      'app',
      '--device',
      params.deviceId,
      params.appPath,
    ];
    
    await this.executeCommand(args);
    
    return {
      deviceId: params.deviceId,
      appPath: params.appPath,
      installed: true,
    };
  }

  private async launchAppOnDevice(params: z.infer<typeof LaunchAppOnDeviceSchema>) {
    const args = [
      this.simctlPath,
      'devicectl',
      'device',
      'process',
      'launch',
      '--device',
      params.deviceId,
      params.bundleId,
    ];
    
    if (params.waitForDebugger) {
      args.push('--wait-for-debugger');
    }
    
    const result = await this.executeCommand(args);
    
    return {
      deviceId: params.deviceId,
      bundleId: params.bundleId,
      launched: true,
      output: result.stdout,
    };
  }

  private async getBundleId(params: z.infer<typeof GetBundleIdSchema>) {
    const plistPath = path.join(params.appPath, 'Info.plist');
    
    try {
      const args = [
        '/usr/libexec/PlistBuddy',
        '-c',
        'Print :CFBundleIdentifier',
        plistPath,
      ];
      
      const result = await this.executeCommand(args);
      const bundleId = result.stdout.trim();
      
      return {
        bundleId,
        appPath: params.appPath,
      };
    } catch (error) {
      throw new ResourceNotFoundError(`Could not read bundle ID from ${params.appPath}`);
    }
  }

  private async createProject(params: z.infer<typeof CreateProjectSchema>) {
    // This is a simplified implementation
    // In a real implementation, you might use templates or scaffold tools
    
    const projectPath = path.join(params.path, params.name);
    
    // Create directory structure
    await fs.mkdir(projectPath, { recursive: true });
    
    // Initialize git if requested
    if (params.includeGit) {
      await this.executeCommand(['git', 'init'], { cwd: projectPath });
    }
    
    // Create a basic Package.swift for Swift projects
    if (params.language === 'Swift') {
      const packageContent = `// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "${params.name}",
    platforms: [
        .${params.platform.toLowerCase()}(.v${params.platform === 'iOS' ? '17' : '14'})
    ],
    products: [
        .library(
            name: "${params.name}",
            targets: ["${params.name}"]
        ),
    ],
    targets: [
        .target(
            name: "${params.name}",
            dependencies: []
        ),
        ${params.includeTests ? `.testTarget(
            name: "${params.name}Tests",
            dependencies: ["${params.name}"]
        ),` : ''}
    ]
)`;
      
      await fs.writeFile(path.join(projectPath, 'Package.swift'), packageContent);
    }
    
    return {
      projectPath,
      name: params.name,
      bundleId: params.bundleId,
      platform: params.platform,
      created: true,
    };
  }

  private async listRunningProcesses() {
    const processes = Array.from(this.runningProcesses.entries()).map(([id, process]) => ({
      id,
      pid: process.pid,
      running: !process.killed,
    }));
    
    return {
      processes,
      count: processes.length,
    };
  }

  private async stopProcess(processId: string) {
    const process = this.runningProcesses.get(processId);
    
    if (!process) {
      throw new ResourceNotFoundError(`Process ${processId} not found`);
    }
    
    process.kill();
    this.runningProcesses.delete(processId);
    
    return {
      processId,
      stopped: true,
    };
  }

  protected getCustomMethods(): string[] {
    return ['getXcodeVersion', 'getAvailableSDKs', 'validateProject'];
  }

  protected async handleCustomMethod(method: string, params: unknown): Promise<unknown> {
    switch (method) {
      case 'getXcodeVersion':
        return this.getXcodeVersion();
      case 'getAvailableSDKs':
        return this.getAvailableSDKs();
      case 'validateProject':
        return this.validateProject(params as any);
      default:
        return super.handleCustomMethod(method, params);
    }
  }

  private async getXcodeVersion() {
    const result = await this.executeCommand([this.xcodebuildPath, '-version']);
    const versionMatch = result.stdout.match(/Xcode (\d+\.\d+(?:\.\d+)?)/);
    const buildMatch = result.stdout.match(/Build version (\w+)/);
    
    return {
      version: versionMatch ? versionMatch[1] : 'unknown',
      build: buildMatch ? buildMatch[1] : 'unknown',
      fullOutput: result.stdout.trim(),
    };
  }

  private async getAvailableSDKs() {
    const result = await this.executeCommand([this.xcodebuildPath, '-showsdks']);
    
    const sdks: Array<{ name: string; version: string; platform: string }> = [];
    const lines = result.stdout.split('\n');
    
    for (const line of lines) {
      const match = line.match(/\s+-sdk\s+(\w+)(\d+\.\d+)/);
      if (match) {
        sdks.push({
          name: match[1],
          version: match[2],
          platform: match[1].includes('ios') ? 'iOS' : 
                   match[1].includes('macos') ? 'macOS' :
                   match[1].includes('tvos') ? 'tvOS' :
                   match[1].includes('watchos') ? 'watchOS' : 'unknown',
        });
      }
    }
    
    return {
      sdks,
      count: sdks.length,
    };
  }

  private async validateProject(params: { projectPath: string }) {
    try {
      const stats = await fs.stat(params.projectPath);
      
      if (!stats.isDirectory()) {
        return {
          valid: false,
          error: 'Path is not a directory',
        };
      }
      
      const isWorkspace = params.projectPath.endsWith('.xcworkspace');
      const isProject = params.projectPath.endsWith('.xcodeproj');
      
      if (!isWorkspace && !isProject) {
        return {
          valid: false,
          error: 'Path is not an Xcode project or workspace',
        };
      }
      
      // Try to list schemes to validate it's a real project
      const schemes = await this.listSchemes({ projectPath: params.projectPath });
      
      return {
        valid: true,
        type: isWorkspace ? 'workspace' : 'project',
        schemes: schemes.schemes,
      };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }
}