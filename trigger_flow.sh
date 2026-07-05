#!/bin/bash
set -e

if [ -z "$1" ]; then
  echo "Usage: bash trigger_flow.sh <endpoint-url>"
  echo "Example: bash trigger_flow.sh https://b640c356trial.it-cpitrial05-rt.cfapps.us10-001.hana.ondemand.com/http/testtimeout"
  exit 1
fi

ENDPOINT="$1"

read -p "SAP BTP username (email): " CPI_USER
read -s -p "SAP BTP password: " CPI_PASS
echo
echo

COOKIE_JAR=$(mktemp)

echo "=== Step 1: Fetching CSRF token ==="
CSRF_RESPONSE=$(curl -sS -i -c "$COOKIE_JAR" -u "$CPI_USER:$CPI_PASS" -H "X-CSRF-Token: Fetch" "$ENDPOINT")
echo "$CSRF_RESPONSE"
CSRF_TOKEN=$(echo "$CSRF_RESPONSE" | grep -i "^X-CSRF-Token:" | awk '{print $2}' | tr -d '\r')

if [ -z "$CSRF_TOKEN" ]; then
  echo ""
  echo "No CSRF token returned — likely still an auth failure (check the status code above)."
  rm -f "$COOKIE_JAR"
  exit 1
fi

echo ""
echo "Got CSRF token: $CSRF_TOKEN"
echo ""
echo "=== Step 2: Triggering the flow (POST) ==="
curl -sS -i -b "$COOKIE_JAR" -u "$CPI_USER:$CPI_PASS" -H "X-CSRF-Token: $CSRF_TOKEN" -X POST "$ENDPOINT"

rm -f "$COOKIE_JAR"
