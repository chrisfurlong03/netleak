"""netleak: how much benchmark accuracy survives removing identifier-like packet fields?

Pipeline: pcapML file -> `load` (samples) -> `encode`/`features` (cached nPrint bits and
hand features) -> `rungs` (feature restriction R0-R3) -> `splits` -> `models` ->
`evaluate`/`results` (JSON under results/) -> `plots`. `runner` ties it together and
`cli` exposes it as the `netleak` command. See AGENTS.md for the module map.
"""

__version__ = "0.1.0"
