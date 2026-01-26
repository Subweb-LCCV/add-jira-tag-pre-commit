#!/usr/bin/env bash

# Git will pass the commit msg as an argument to prepare-commit-msg hook.
# See https://git-scm.com/docs/githooks#_prepare_commit_msg.
commit_msg_filepath=$1

branch_name=$(git branch --show-current)

regex="fb-([A-Z]+-[0-9]+)(-.*)?"
if [[ $branch_name =~ $regex ]]
then
    jira_issue=${BASH_REMATCH[1]}
else
    echo Branch is not in format 'fb-{JIRA_TAG}'. Skipping...
    exit 0
fi

# Skip fixup/squash/amend commits and merge commits - they should not be modified.
title_line=$(head -1 "$commit_msg_filepath")
if [[ "$title_line" =~ ^(fixup!|squash!|amend!|Merge\ ) ]]
then
    echo Skipping fixup/squash/amend/merge commit...
    exit 0
fi

# Check for old format (any JIRA tag alone as last non-blank line).
# Use the old tag instead of branch tag to preserve original association during rebases.
last_content_line=$(grep -v '^[[:space:]]*$' "$commit_msg_filepath" | tail -1)
if [[ "$last_content_line" =~ ^[A-Z]+-[0-9]+$ ]]
then
    old_tag=${BASH_REMATCH[0]}
    echo Converting old format tag \'$old_tag\' to new format...
    # Remove the trailing tag line using tac/sed/tac.
    tac "$commit_msg_filepath" | sed "0,/^${old_tag}$/d" | tac > "${commit_msg_filepath}.tmp"
    mv "${commit_msg_filepath}.tmp" "$commit_msg_filepath"
    # Remove trailing blank lines.
    while [[ $(tail -c 1 "$commit_msg_filepath" | wc -l) -gt 0 ]] && \
          [[ -z $(tail -1 "$commit_msg_filepath" | tr -d '[:space:]') ]]
    do
        head -n -1 "$commit_msg_filepath" > "${commit_msg_filepath}.tmp"
        mv "${commit_msg_filepath}.tmp" "$commit_msg_filepath"
    done
    # Add the OLD tag (not branch tag) to title, unless title already has a tag.
    title_line=$(head -1 "$commit_msg_filepath")
    if [[ ! "$title_line" =~ ^\[[A-Z]+-[0-9]+\] ]]
    then
        sed -i "1s/^/[$old_tag] /" "$commit_msg_filepath" 2>/dev/null || \
            sed -i '' "1s/^/[$old_tag] /" "$commit_msg_filepath"
    fi
    exit 0
fi

# Check if any JIRA-style tag already in title (handles rebased commits from other branches).
title_line=$(head -1 "$commit_msg_filepath")
if [[ "$title_line" =~ ^\[[A-Z]+-[0-9]+\] ]]
then
    echo JIRA tag already in title. Skipping...
    exit 0
fi

# Add tag to beginning of title.
echo Adding tag \'[$jira_issue]\' to commit message title
# Use sed to prepend tag to first line, preserving file structure.
sed -i "1s/^/[$jira_issue] /" "$commit_msg_filepath" 2>/dev/null || \
    sed -i '' "1s/^/[$jira_issue] /" "$commit_msg_filepath"
exit 0
