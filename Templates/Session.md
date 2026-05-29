---
type: session
project: <% tp.file.cursor(1) %>
session_id: ""
path: ""
start: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
end: ""
message_count: 0
tools: []
status: active
summary: ""
branch: ""
cc_version: ""
model: ""
tokens: 0
source: manual
---
> [!info] Manual session note. The sync script fills frontmatter for auto-detected sessions; everything above `## Notes` is machine-owned, everything below is yours.

## Notes

<% tp.file.cursor(2) %>
