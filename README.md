# Blocky UI

Blocky UI is a small Streamlit application for managing the dynamic parts of
[Blocky](https://github.com/0xERR0R/blocky)'s DNS blocking configuration. It
provides a web interface for deny/allow lists, schedules, and per-client list
assignments. The application stores its own state in JSON and writes the
resulting `blocking` configuration to a YAML file when **Deploy configuration
to Blocky** is clicked.

## Docker Compose

[`compose.example.yml`](compose.example.yml) runs three services:

1. `blocky` serves DNS and reads all YAML files from a configuration directory.
2. `blocky-blocking-editor` edits the parental-control rules and writes
   `20_parental_generated.yml` into that same directory.
3. `blocky-watcher` watches the generated file and restarts `blocky` after the
   UI changes it, causing Blocky to load the new configuration.

Create the bind-mount directories before starting the stack:

```sh
mkdir -p runtime/blocky-config runtime/blocky-blocking-editor
```

Put the hand-maintained Blocky configuration in a separate file such as
`runtime/blocky-config/10_blocky.yml`:

```yaml
upstreams:
  groups:
    default:
      - 1.1.1.1
      - 9.9.9.9

ports:
  dns: 53
  http: 4000

blocking:
  # Settings here are not editable through Blocky UI.
  loading:
    refreshPeriod: 4h

  # Static lists and assignments may also live here.
  denylists:
    always-blocked:
      - https://example.org/always-blocked.txt
  clientGroupsBlock:
    default:
      - always-blocked
```

The base file should contain everything outside `blocking`, plus any
`blocking` settings that must remain hand-maintained rather than editable in
the UI. Do not edit `20_parental_generated.yml`: Blocky UI replaces it on each
deployment.

`BLOCKY_CONFIG_FILE` points Blocky at the directory, not an individual file.
Blocky loads its YAML files in lexical order and merges mappings recursively,
so the `blocking` maps in `10_blocky.yml` and
`20_parental_generated.yml` become one effective configuration. If both files
set the same scalar or list, the value from the later file wins; lists are
replaced rather than concatenated. Use different names for static and
UI-managed lists unless you intentionally want the generated definition to
override the static one. See Blocky's
[multiple configuration files documentation](https://0xerr0r.github.io/blocky/main/configuration/#multiple-configuration-files)
for the complete merge rules.

Start the example with:

```sh
docker compose -f compose.example.yml up -d
```

The UI is then available at <http://localhost:8080>. Adjust the published
ports, timezone, image version, and networking in the example for your
environment.

### Watcher behavior and security

The watcher listens for completed writes or replacements of
`20_parental_generated.yml`. When one occurs, it runs `docker restart blocky`
through the Docker socket. This is a restart rather than a live reload: Blocky
reads and merges the whole configuration directory again during startup.

Mounting `/var/run/docker.sock` gives the watcher highly privileged access to
the Docker daemon. Only run trusted images and configuration on that host. For
a more locked-down deployment, replace the direct socket mount with a Docker
socket proxy that only permits the required restart operation.
