#!/bin/sh
set -eu

: "${NETLIFY_PROXY_URL:?NETLIFY_PROXY_URL is required}"
: "${NETLIFY_SITE_ID:?NETLIFY_SITE_ID is required}"

cd /app/frontend/dist
zip -qr /tmp/world-engine-site.zip .

curl --fail-with-body --silent --show-error \
  -A "netlify-mcp" \
  -F "zip=@/tmp/world-engine-site.zip;type=application/zip" \
  "${NETLIFY_PROXY_URL}/api/v1/sites/${NETLIFY_SITE_ID}/builds"

echo
echo "NETLIFY_UPLOAD_COMPLETE"
