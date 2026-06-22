# Recipe: Scaffold a runnable Logos Execution Zone (LEZ) app with `lgs`

**Component:** `logos-blockchain` (LEZ / Logos Execution Environment) via `logos-co/scaffold` (`lgs`).
Don't hand-roll project setup — `lgs` bootstraps a fully runnable LEZ `program_deployment` project.

> Via this server you can drive `lgs` with the `logos_scaffold` MCP tool (allowlisted actions:
> version, help, create, new, init, doctor, build, localnet_status).

## Install the CLI
```bash
cargo install --git https://github.com/logos-co/scaffold
# installs two equivalent binaries: `logos-scaffold` and `lgs`
```

## Bootstrap → run → deploy
```bash
lgs create my-app          # scaffold a standalone LEZ project
cd my-app
lgs setup                  # fetch logos-blockchain-circuits etc. (first run)
lgs localnet start         # start a local sequencer
lgs build                  # build the program
lgs deploy                 # deploy to the localnet
lgs run --watch            # run + redeploy on change
lgs doctor                 # diagnose environment issues
```

## Notes
- Single external dependency: LEZ (`logos-blockchain/logos-execution-zone`); standalone sequencer flow.
- Unix-only; needs `git`, `rustc`/`cargo`, `lsof`/`ps`/`kill`, and Docker/Podman for guest builds.
- Example programs to learn from: `logos-blockchain/lez-programs`, `logos-blockchain/logos-sql-zone`.

## Sources
- `logos-co/scaffold` (the `lgs` CLI), `logos-blockchain/logos-execution-zone`, `logos-blockchain/lez-programs`
