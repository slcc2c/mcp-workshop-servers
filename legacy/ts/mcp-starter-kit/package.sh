#!/bin/bash
# Package MCP Starter Kit for distribution

set -e

PACKAGE_NAME="mcp-starter-kit"
VERSION="1.0.0"
OUTPUT_DIR="dist"

echo "📦 Packaging MCP Starter Kit v${VERSION}"
echo "===================================="

# Create dist directory
mkdir -p "$OUTPUT_DIR"

# Create package directory
PACKAGE_DIR="${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}"
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# Copy files
echo "Copying files..."
cp -r README.md "$PACKAGE_DIR/"
cp -r setup.sh "$PACKAGE_DIR/"
cp -r setup-with-1password.sh "$PACKAGE_DIR/"
cp -r scripts/ "$PACKAGE_DIR/"
cp -r docs/ "$PACKAGE_DIR/" 2>/dev/null || mkdir -p "$PACKAGE_DIR/docs"
cp -r examples/ "$PACKAGE_DIR/" 2>/dev/null || mkdir -p "$PACKAGE_DIR/examples"
cp LICENSE "$PACKAGE_DIR/"
cp .gitignore "$PACKAGE_DIR/"

# Ensure scripts are executable
chmod +x "$PACKAGE_DIR"/*.sh 2>/dev/null || true
find "$PACKAGE_DIR/scripts" -name "*.sh" -type f -exec chmod +x {} \; 2>/dev/null || true

# Create archive
echo "Creating archive..."
cd "$OUTPUT_DIR"
tar -czf "${PACKAGE_NAME}-${VERSION}.tar.gz" "${PACKAGE_NAME}-${VERSION}"
zip -qr "${PACKAGE_NAME}-${VERSION}.zip" "${PACKAGE_NAME}-${VERSION}"

# Calculate checksums
echo "Calculating checksums..."
if command -v shasum &> /dev/null; then
    shasum -a 256 "${PACKAGE_NAME}-${VERSION}.tar.gz" > "${PACKAGE_NAME}-${VERSION}.tar.gz.sha256"
    shasum -a 256 "${PACKAGE_NAME}-${VERSION}.zip" > "${PACKAGE_NAME}-${VERSION}.zip.sha256"
fi

# Clean up
rm -rf "${PACKAGE_NAME}-${VERSION}"

echo
echo "✅ Package created successfully!"
echo
echo "Files created:"
echo "  - ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz"
echo "  - ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.zip"
if [ -f "${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz.sha256" ]; then
    echo "  - ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.tar.gz.sha256"
    echo "  - ${OUTPUT_DIR}/${PACKAGE_NAME}-${VERSION}.zip.sha256"
fi
echo
echo "Distribution instructions:"
echo "1. Upload to GitHub Releases"
echo "2. Share download link"
echo "3. Users extract and run ./setup.sh"