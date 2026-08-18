#!/bin/bash

# Run this script from anywhere or from backend/
BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Starting all services..."

# 1. Start Redis daemon
redis-server --daemonize yes > /dev/null 2>&1
echo "✅ Redis started on localhost:6379"

# 2. Start Qdrant detached process
cd "$BACKEND_DIR/qdrant" || exit 1
(nohup ./qdrant > qdrant.log 2>&1 & disown)
echo "✅ Qdrant started on localhost:6333"

# Wait 3s for startup
sleep 3

echo ""
echo "✅ All services status check:"
redis-cli ping > /dev/null 2>&1 && echo "   Redis  (6379) → PONG ✅" || echo "   Redis  (6379) → DOWN ❌"
curl -s http://localhost:6333/collections > /dev/null 2>&1 && echo "   Qdrant (6333) → OK ✅" || echo "   Qdrant (6333) → DOWN ❌"
echo ""
