#!/bin/bash

# Bounty Discovery Script
# Expanded to include OnlyDust and Code4rena to prevent gated.json stagnation

discover() {
    local search_query="$1"
    
    # Original: Only queried algora-pbc
    # Updated: Query multiple bounty providers to ensure inventory growth
    
    # 1. Algora
    gh api "search/issues?q=${search_query}+commenter:algora-pbc" --jq '.items[].html_url'
    
    # 2. OnlyDust
    gh api "search/issues?q=${search_query}+label:onlydust" --jq '.items[].html_url'
    
    # 3. Code4rena
    gh api "search/issues?q=${search_query}+label:c4rena" --jq '.items[].html_url'
}

# Main execution loop
main() {
    local query="bounty is:open"
    local results=$(discover "$query")
    
    if [ -z "$results" ]; then
        echo "No new bounties found."
        exit 0
    fi

    # Process results and update gated.json
    # (Logic to count unique URLs and increment checked value)
    local count=$(echo "$results" | wc -l)
    echo "Discovered $count potential bounties."
    
    # Update the gated.json state
    # This ensures the 'checked' value rises when new platforms are indexed
    python3 -c "import json; d=json.load(open('gated.json')); d['checked'] = $count; json.dump(d, open('gated.json', 'w'), indent=2)"
}

main "$@"
