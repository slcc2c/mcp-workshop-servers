# Advanced MCP Servers

This document covers the Tier 3 advanced servers: Neo4j, Jupyter, and XcodeBuildMCP.

## Neo4j Graph Database Server

The Neo4j server provides comprehensive graph database operations using the Cypher query language.

### Features
- Full Cypher query support
- Node and relationship management
- Graph traversal and pathfinding
- Schema management (indexes, constraints)
- Graph algorithms (requires GDS plugin)
- Transaction support

### Configuration

```bash
# Connection settings in .env
NEO4J_URL=bolt://localhost:7687    # or neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j               # Default database

# Or use 1Password
NEO4J_URL=1password:Server-Configurations/Neo4j Connection:notesPlain
NEO4J_USER=1password:Server-Configurations/Neo4j User:notesPlain
NEO4J_PASSWORD=1password:Server-Configurations/Neo4j Password:notesPlain
```

### Available Tools (13)

#### Query Operations
- `neo4j_query` - Execute any Cypher query
- `neo4j_schema` - Get database schema information
- `neo4j_stats` - Get database statistics

#### Node Operations
- `neo4j_create_node` - Create nodes with labels and properties
- `neo4j_find_nodes` - Find nodes by labels and properties
- `neo4j_update_node` - Update node properties
- `neo4j_delete_node` - Delete nodes (with optional relationship deletion)

#### Relationship Operations
- `neo4j_create_relationship` - Create relationships between nodes
- `neo4j_find_path` - Find shortest path or all paths between nodes

#### Schema Management
- `neo4j_create_index` - Create indexes (btree, fulltext, point, range)
- `neo4j_create_constraint` - Create constraints (unique, exists, key)

#### Advanced
- `neo4j_algorithm` - Run graph algorithms (PageRank, community detection, etc.)

### Usage Examples

#### Create a Social Network
```
Tool: neo4j_create_node
Input: {
  "labels": ["Person"],
  "properties": {
    "name": "Alice",
    "age": 30,
    "city": "New York"
  }
}

Tool: neo4j_create_relationship
Input: {
  "fromNode": {"labels": ["Person"], "properties": {"name": "Alice"}},
  "toNode": {"labels": ["Person"], "properties": {"name": "Bob", "age": 25}},
  "type": "FRIENDS_WITH",
  "properties": {"since": 2020}
}
```

#### Find Shortest Path
```
Tool: neo4j_find_path
Input: {
  "startNode": {"labels": ["Person"], "properties": {"name": "Alice"}},
  "endNode": {"labels": ["Person"], "properties": {"name": "Charlie"}},
  "relationshipTypes": ["FRIENDS_WITH", "KNOWS"],
  "maxLength": 5,
  "algorithm": "shortest"
}
```

#### Run PageRank Algorithm
```
Tool: neo4j_algorithm
Input: {
  "algorithm": "pagerank",
  "nodeLabel": "Person",
  "relationshipType": "FOLLOWS",
  "writeProperty": "pagerank"
}
```

#### Complex Cypher Query
```
Tool: neo4j_query
Input: {
  "query": "MATCH (p:Person)-[:ACTED_IN]->(m:Movie)<-[:DIRECTED]-(d:Person) WHERE m.year > $year RETURN p.name, m.title, d.name LIMIT 10",
  "params": {"year": 2000}
}
```

### Best Practices

1. **Use Indexes**: Create indexes on frequently queried properties
2. **Batch Operations**: Use Cypher for bulk inserts
3. **Parameterized Queries**: Always use parameters to prevent injection
4. **Relationship Direction**: Be consistent with relationship directions
5. **Property Types**: Use appropriate data types for properties

## Jupyter Notebook Server

The Jupyter server provides notebook execution and data science capabilities.

### Features
- Create and manage Jupyter notebooks
- Execute code cells with kernel management
- Variable inspection and visualization
- Plot generation with matplotlib
- Export to multiple formats (HTML, PDF, Markdown, Python)
- Multiple kernel support

### Configuration

```bash
# Jupyter settings in .env
JUPYTER_PORT=8888
JUPYTER_TOKEN=your-token-here    # Optional, for security

# Or use 1Password
JUPYTER_TOKEN=1password:Server-Configurations/Jupyter Token:notesPlain
```

### Available Tools (11)

#### Notebook Management
- `jupyter_create_notebook` - Create new notebooks
- `jupyter_open_notebook` - Open notebook and start kernel session
- `jupyter_save_notebook` - Save notebook with current state
- `jupyter_export` - Export to HTML, PDF, Markdown, or Python

#### Code Execution
- `jupyter_execute_cell` - Execute code or markdown cells
- `jupyter_execute_notebook` - Execute entire notebook with parameters
- `jupyter_get_variable` - Inspect variable values
- `jupyter_plot` - Create matplotlib plots

#### Kernel Management
- `jupyter_list_kernels` - List available kernels
- `jupyter_kernel_control` - Interrupt, restart, or shutdown kernels
- `jupyter_list_sessions` - List active notebook sessions

### Usage Examples

#### Create and Execute Notebook
```
Tool: jupyter_create_notebook
Input: {
  "name": "data_analysis",
  "directory": "./notebooks",
  "kernelName": "python3"
}

Tool: jupyter_open_notebook
Input: {
  "path": "./notebooks/data_analysis.ipynb"
}

Tool: jupyter_execute_cell
Input: {
  "notebookId": "session-id-here",
  "code": "import pandas as pd\nimport numpy as np\ndata = pd.read_csv('data.csv')"
}
```

#### Create Visualizations
```
Tool: jupyter_plot
Input: {
  "notebookId": "session-id-here",
  "plotType": "scatter",
  "data": {
    "x": [1, 2, 3, 4, 5],
    "y": [2, 4, 6, 8, 10]
  },
  "options": {
    "title": "Linear Relationship",
    "xlabel": "X Values",
    "ylabel": "Y Values",
    "figsize": [8, 6]
  }
}
```

#### Execute with Parameters
```
Tool: jupyter_execute_notebook
Input: {
  "path": "./notebooks/report_template.ipynb",
  "parameters": {
    "start_date": "2025-01-01",
    "end_date": "2025-06-30",
    "output_dir": "./reports"
  },
  "timeout": 600
}
```

#### Variable Inspection
```
Tool: jupyter_get_variable
Input: {
  "notebookId": "session-id-here",
  "variableName": "df"
}
// Returns: type, shape, length, preview of value
```

### Data Science Workflows

#### 1. Exploratory Data Analysis
```python
# Load data
df = pd.read_csv('sales_data.csv')

# Basic statistics
df.describe()

# Check for missing values
df.isnull().sum()

# Visualize distributions
df['revenue'].hist(bins=50)
```

#### 2. Machine Learning Pipeline
```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

# Prepare data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Train model
model = RandomForestClassifier()
model.fit(X_train, y_train)

# Evaluate
accuracy = model.score(X_test, y_test)
```

#### 3. Report Generation
```python
# Generate report
from datetime import datetime

report = f"""
# Analysis Report
Generated: {datetime.now()}

## Key Findings
- Total revenue: ${revenue:,.2f}
- Growth rate: {growth:.1%}
"""

# Export to HTML
with open('report.html', 'w') as f:
    f.write(markdown.markdown(report))
```

### Best Practices

1. **Session Management**: Close kernels when done to free resources
2. **Cell Organization**: Keep cells focused on single tasks
3. **Documentation**: Use markdown cells for explanations
4. **Version Control**: Save notebooks regularly
5. **Resource Limits**: Monitor memory usage for large datasets

## Integration Examples

### Neo4j + Jupyter: Graph Analytics
```python
# In Jupyter
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

# Query Neo4j from Jupyter
with driver.session() as session:
    result = session.run("""
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        RETURN p.name, COUNT(m) as movies
        ORDER BY movies DESC
        LIMIT 10
    """)
    
    data = [(r['p.name'], r['movies']) for r in result]

# Visualize in Jupyter
import matplotlib.pyplot as plt

names, counts = zip(*data)
plt.bar(names, counts)
plt.xticks(rotation=45)
plt.title('Top 10 Actors by Movie Count')
plt.show()
```

### Combined Workflow: Data Pipeline
1. Load data from PostgreSQL
2. Process in Jupyter notebooks
3. Store relationships in Neo4j
4. Cache results in Redis
5. Deploy model with Kubernetes

## Troubleshooting

### Neo4j Issues

**Connection Refused**
- Check Neo4j is running: `neo4j status`
- Verify bolt port is open (7687)
- Check authentication settings

**Algorithm Not Found**
- Install Graph Data Science plugin
- Restart Neo4j after installation

### Jupyter Issues

**Kernel Won't Start**
- Check Python environment
- Verify Jupyter is installed: `pip install jupyter`
- Check kernel specs: `jupyter kernelspec list`

**Plot Not Showing**
- Ensure matplotlib is installed
- Use `%matplotlib inline` magic command
- Check backend configuration

**Export Failed**
- Install pandoc for PDF export
- Check nbconvert is installed
- Verify output directory exists

## Performance Optimization

### Neo4j
- Create composite indexes for multi-property queries
- Use native IDs when possible
- Batch operations in transactions
- Profile queries with `EXPLAIN` and `PROFILE`

### Jupyter
- Use efficient data structures (numpy arrays)
- Clear output of large cells
- Use generators for large datasets
- Consider Dask for parallel processing

## Security Considerations

### Neo4j
- Use strong passwords
- Enable SSL/TLS for connections
- Restrict database access with roles
- Audit query logs

### Jupyter
- Always use token authentication
- Run on localhost only (not 0.0.0.0)
- Use JupyterHub for multi-user setups
- Sanitize notebook outputs before sharing

## XcodeBuildMCP Server

The XcodeBuildMCP server provides comprehensive iOS/macOS development capabilities through Xcode integration.

### Features
- Xcode project and workspace management
- Swift package dependency management
- iOS simulator control and automation
- Physical device detection and app deployment
- Build configuration and scheme management
- Code signing verification
- App bundle information extraction

### Requirements
- **Platform**: macOS 12.0 or later
- **Xcode**: Version 14.0 or later
- **Command Line Tools**: Must be installed (`xcode-select --install`)
- **Developer Account**: Required for physical device deployment

### Configuration

```bash
# XcodeBuildMCP uses the system's Xcode installation
# No additional configuration required

# Verify Xcode installation
xcode-select -p
# Should output: /Applications/Xcode.app/Contents/Developer

# Install Command Line Tools if needed
xcode-select --install

# For physical device deployment, ensure:
# 1. Valid provisioning profiles in Xcode
# 2. Developer certificate installed
# 3. Device registered in Apple Developer portal
```

### Available Tools (25+)

#### Xcode Project Management (5 tools)
- `xcode_list_projects` - List all Xcode projects in a directory
- `xcode_project_info` - Get detailed project information
- `xcode_list_targets` - List all targets in a project
- `xcode_list_schemes` - List available schemes
- `xcode_list_configurations` - List build configurations

#### Swift Package Manager (6 tools)
- `swift_package_init` - Initialize a new Swift package
- `swift_package_add_dependency` - Add a package dependency
- `swift_package_remove_dependency` - Remove a package dependency
- `swift_package_update` - Update package dependencies
- `swift_package_resolve` - Resolve package dependencies
- `swift_package_list_dependencies` - List current dependencies

#### iOS Simulator Control (8 tools)
- `simulator_list` - List all available simulators
- `simulator_create` - Create a new simulator
- `simulator_delete` - Delete a simulator
- `simulator_boot` - Boot a simulator
- `simulator_shutdown` - Shutdown a simulator
- `simulator_install_app` - Install an app on simulator
- `simulator_launch_app` - Launch an app on simulator
- `simulator_uninstall_app` - Uninstall an app from simulator

#### Physical Device Management (4 tools)
- `device_list` - List connected physical devices
- `device_info` - Get detailed device information
- `device_install_app` - Install app on physical device
- `device_launch_app` - Launch app on physical device

#### App Utilities (2 tools)
- `app_info` - Get app bundle information
- `codesign_verify` - Verify code signing status

### Usage Examples

#### Project Discovery and Analysis
```
Tool: xcode_list_projects
Input: {
  "directory": "/Users/developer/Projects"
}
// Returns list of .xcodeproj and .xcworkspace files

Tool: xcode_project_info
Input: {
  "projectPath": "/Users/developer/Projects/MyApp/MyApp.xcodeproj"
}
// Returns: targets, configurations, SDK version, deployment target
```

#### Swift Package Management
```
Tool: swift_package_init
Input: {
  "directory": "/Users/developer/MyPackage",
  "type": "library",
  "name": "MyAwesomeKit"
}

Tool: swift_package_add_dependency
Input: {
  "projectPath": "/Users/developer/MyApp",
  "url": "https://github.com/Alamofire/Alamofire.git",
  "version": "5.8.0"
}

Tool: swift_package_update
Input: {
  "projectPath": "/Users/developer/MyApp"
}
```

#### Simulator Workflows
```
# Create and configure a new simulator
Tool: simulator_create
Input: {
  "name": "iPhone 15 Pro Test",
  "deviceType": "iPhone 15 Pro",
  "runtime": "iOS 17.0"
}

# Boot the simulator
Tool: simulator_boot
Input: {
  "simulatorId": "ABCD-1234-5678-EFGH"
}

# Install your app
Tool: simulator_install_app
Input: {
  "simulatorId": "ABCD-1234-5678-EFGH",
  "appPath": "/path/to/DerivedData/Build/Products/Debug-iphonesimulator/MyApp.app"
}

# Launch the app
Tool: simulator_launch_app
Input: {
  "simulatorId": "ABCD-1234-5678-EFGH",
  "bundleId": "com.company.myapp"
}
```

#### Physical Device Deployment
```
# List connected devices
Tool: device_list
// Returns: device name, UDID, model, iOS version

# Get device details
Tool: device_info
Input: {
  "deviceId": "00008110-000A1234567890AB"
}

# Install app on device
Tool: device_install_app
Input: {
  "deviceId": "00008110-000A1234567890AB",
  "appPath": "/path/to/MyApp.ipa"
}
```

#### Code Signing Verification
```
Tool: codesign_verify
Input: {
  "appPath": "/path/to/MyApp.app"
}
// Returns: signing certificate, team ID, entitlements, provisioning profile
```

### Common Workflows

#### 1. CI/CD Pipeline Integration
```python
# Example: Automated testing workflow
async def run_tests():
    # List available simulators
    simulators = await xcode.simulator_list()
    
    # Find or create test simulator
    test_sim = find_simulator("iPhone 15", "iOS 17.0")
    if not test_sim:
        test_sim = await xcode.simulator_create({
            "name": "CI Test Device",
            "deviceType": "iPhone 15",
            "runtime": "iOS 17.0"
        })
    
    # Boot simulator
    await xcode.simulator_boot({"simulatorId": test_sim.id})
    
    # Build and install app
    await build_app("MyApp.xcodeproj", "Debug")
    await xcode.simulator_install_app({
        "simulatorId": test_sim.id,
        "appPath": get_app_path()
    })
    
    # Run UI tests
    await run_ui_tests(test_sim.id)
    
    # Cleanup
    await xcode.simulator_shutdown({"simulatorId": test_sim.id})
```

#### 2. Multi-Device Testing
```javascript
// Test on multiple iOS versions
const devices = [
    { name: "iPhone 15 iOS 17", device: "iPhone 15", os: "iOS 17.0" },
    { name: "iPhone 14 iOS 16", device: "iPhone 14", os: "iOS 16.4" },
    { name: "iPad Pro", device: "iPad Pro (12.9-inch)", os: "iPadOS 17.0" }
];

for (const config of devices) {
    // Create simulator
    const sim = await xcode.simulatorCreate({
        name: config.name,
        deviceType: config.device,
        runtime: config.os
    });
    
    // Run tests
    await testOnDevice(sim.id);
}
```

#### 3. Swift Package Development
```bash
# Create a new Swift package
xcode.swift_package_init({
    directory: "./MyLibrary",
    type: "library",
    name: "NetworkingKit"
})

# Add dependencies
xcode.swift_package_add_dependency({
    projectPath: "./MyLibrary",
    url: "https://github.com/Alamofire/Alamofire.git",
    version: "5.8.0"
})

# Build and test
swift build
swift test
```

### Best Practices

1. **Simulator Management**
   - Clean up unused simulators regularly
   - Use consistent naming conventions
   - Boot simulators before installing apps
   - Shutdown simulators when done to free resources

2. **App Deployment**
   - Verify code signing before deployment
   - Use correct provisioning profiles
   - Test on multiple device types
   - Check app info for correct bundle ID

3. **Swift Packages**
   - Pin dependency versions for stability
   - Regularly update dependencies
   - Use semantic versioning
   - Test package integration thoroughly

4. **Build Configuration**
   - Use different schemes for Debug/Release
   - Configure build settings appropriately
   - Enable optimizations for Release builds
   - Use xcconfig files for shared settings

### Troubleshooting

#### Common Issues

**"No simulators available"**
- Ensure Xcode is installed and opened at least once
- Download additional simulators in Xcode preferences
- Check `xcrun simctl list` output

**"Code signing failed"**
- Verify developer certificate is installed
- Check provisioning profile matches bundle ID
- Ensure device UDID is registered
- Run `security find-identity -p codesigning`

**"Device not found"**
- Enable developer mode on device
- Trust computer on device
- Check USB connection
- Verify device is unlocked

**"Swift package resolution failed"**
- Clear package cache: `swift package reset`
- Check network connectivity
- Verify package URL is correct
- Update to latest Swift tools

#### Debug Commands

```bash
# List all simulators
xcrun simctl list

# Check Xcode version
xcodebuild -version

# Verify code signing identity
security find-identity -p codesigning

# List provisioning profiles
ls ~/Library/MobileDevice/Provisioning\ Profiles/

# Check connected devices
xcrun devicectl list devices

# Swift package graph
swift package show-dependencies
```

### Integration with Other MCP Servers

#### GitHub Integration
```javascript
// Clone repo and build iOS app
const repo = await github.cloneRepository({
    owner: "company",
    repo: "ios-app"
});

const projects = await xcode.xcodeListProjects({
    directory: repo.path
});

await xcode.simulatorInstallApp({
    simulatorId: "sim-id",
    appPath: `${repo.path}/build/MyApp.app`
});
```

#### Filesystem Operations
```javascript
// Archive and export app
const buildPath = await filesystem.createDirectory({
    path: "/tmp/builds/MyApp"
});

await xcode.buildAndArchive({
    project: "MyApp.xcodeproj",
    scheme: "MyApp",
    archivePath: `${buildPath}/MyApp.xcarchive`
});
```

### Performance Tips

1. **Simulator Performance**
   - Use hardware keyboard when possible
   - Disable slow animations in simulator
   - Close unnecessary simulators
   - Use smaller device types for faster boot

2. **Build Optimization**
   - Enable parallel builds
   - Use incremental builds
   - Clean build folder periodically
   - Utilize build caching

3. **Testing Efficiency**
   - Run tests in parallel
   - Use test plans for organization
   - Focus on affected tests only
   - Leverage snapshot testing

### Security Considerations

1. **Code Signing**
   - Store certificates in keychain securely
   - Use app-specific passwords
   - Rotate certificates regularly
   - Audit provisioning profiles

2. **Device Security**
   - Only install apps on trusted devices
   - Use development builds for testing only
   - Implement proper entitlements
   - Validate app signatures

3. **Package Dependencies**
   - Audit third-party packages
   - Use specific version tags
   - Review package permissions
   - Monitor for vulnerabilities