# ProjectFlow TODO

## Mobile App

### File Browser in Viewers tab
When a project has `folder_path` set, show a file browser in the Viewers tab using
Nextcloud WebDAV (PROPFIND). Two options to consider:
- **Simple**: Open Nextcloud Files web UI: `{server}/apps/files/?dir=/path` in browser
- **Native**: PROPFIND the folder and render a tap-to-navigate file list in-app

Requires mapping `folder_path` (local desktop path e.g. `~/Nextcloud/Projects/cop`)
to a Nextcloud WebDAV path. Either strip a configurable prefix or add a `mobile_path`
field to the project JSON.
