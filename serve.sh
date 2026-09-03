#!/bin/bash
PORT=${1:-3001}
echo "Serving docs/ at http://localhost:$PORT"
python3 -m http.server $PORT --directory docs
