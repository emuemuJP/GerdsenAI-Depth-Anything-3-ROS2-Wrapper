#!/bin/bash
# Install desktop shortcuts for Depth Anything V3
#
# Usage: bash desktop/install_shortcuts.sh
#
# This script copies .desktop files to your desktop and applications directory.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Installing Depth Anything V3 desktop shortcuts..."
echo ""

# Determine install locations
DESKTOP_DIR="$HOME/Desktop"
APPS_DIR="$HOME/.local/share/applications"

# Create directories if needed
mkdir -p "$APPS_DIR"

# Copy desktop files
for desktop_file in "$SCRIPT_DIR"/*.desktop; do
    if [ -f "$desktop_file" ]; then
        filename=$(basename "$desktop_file")

        # Update the Exec path to use actual repo location
        sed "s|~/depth_anything_3_ros2|$REPO_DIR|g" "$desktop_file" > "/tmp/$filename"

        # Copy to Desktop if it exists
        if [ -d "$DESKTOP_DIR" ]; then
            cp "/tmp/$filename" "$DESKTOP_DIR/"
            chmod +x "$DESKTOP_DIR/$filename"
            echo -e "  ${GREEN}Installed${NC} $DESKTOP_DIR/$filename"
        fi

        # Copy to applications directory
        cp "/tmp/$filename" "$APPS_DIR/"
        chmod +x "$APPS_DIR/$filename"
        echo -e "  ${GREEN}Installed${NC} $APPS_DIR/$filename"

        rm "/tmp/$filename"
    fi
done

echo ""
echo -e "${GREEN}Desktop shortcuts installed successfully!${NC}"
echo ""
echo "You should now see:"
echo "  - 'Depth Anything V3 Demo' - Main demo launcher"
echo "  - 'DA3 RViz2 Viewer' - RViz2 visualization"
echo "  - 'DA3 Performance Monitor' - Performance metrics"
echo ""
echo "Note: You may need to right-click and 'Allow Launching' on desktop icons."
