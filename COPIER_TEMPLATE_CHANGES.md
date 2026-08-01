# Änderungen am Copier-Template

Diese Datei beschreibt die Änderungen, die im Template
[`15r10nk/project-template`](https://github.com/15r10nk/project-template)
vorgenommen werden sollten. Sie basieren auf den Problemen, die beim Update
von Matchify auf Template-Version `v0.1.0` in GitHub Actions aufgetreten sind.

## 1. Coverage-Verzeichnis in allen relevanten Jobs setzen

Die Coverage-Konfiguration verwendet aktuell:

```toml
[tool.coverage.run]
data_file = "$TOP/.coverage"
```

Der `test`-Job muss deshalb `TOP` definieren. Andernfalls versucht
`coverage.py`, Dateien wie `/.coverage.*` im Wurzelverzeichnis anzulegen, und
scheitert wegen fehlender Schreibrechte.

```yaml
jobs:
  test:
    env:
      TOP: ${{github.workspace}}

  coverage:
    env:
      TOP: ${{github.workspace}}
```

Alternativ sollte das Template ganz auf die Umgebungsvariable verzichten und
den Standardpfad `.coverage` relativ zum Arbeitsverzeichnis verwenden. Wichtig
ist, dass Template-Konfiguration und Workflow dieselbe Strategie benutzen.

## 2. Coverage nicht ohne zusätzliche Konfiguration mit pytest-xdist ausführen

Der bisherige Aufruf

```yaml
coverage run -m pytest -n=auto
```

misst nur den xdist-Steuerprozess. Die eigentlichen Tests laufen in
Unterprozessen, sodass leere Coverage-Daten entstehen und der spätere
`coverage html`- beziehungsweise `coverage report`-Schritt mit `No data to
report` scheitert.

Die einfache und robuste Template-Vorgabe sollte deshalb ohne xdist laufen:

```yaml
- name: Test locked dependencies
  run: uv run --locked --with coverage --with pytest -m ${{ matrix.os == 'ubuntu-latest' && 'coverage run -m' || '' }} pytest -vv

- name: Test lowest direct dependencies
  run: uv run --no-sync -m coverage run -m pytest -vv
```

Auch bei der Installation für die `lowest-direct`-Jobs wird dann
`pytest-xdist` nicht benötigt:

```yaml
uv pip install coverage pytest
```

Falls parallele Tests im Template zwingend gewünscht sind, muss stattdessen
die Coverage-Unterprozessmessung vollständig eingerichtet werden, inklusive
separater Datendateien pro Worker und anschließendem `coverage combine`.

## 3. Unterstützte PyPy-Version als Vorgabe verwenden

`pypy3.10` kann die aktuelle Version von LibCST nicht mehr bauen. Deren
Rust/PyO3-Abhängigkeiten setzen mindestens PyPy 3.11 voraus. Die
Copier-Vorgabe und die generierte CI-Matrix sollten daher `pypy3.11` verwenden:

```yaml
pypy_versions:
- pypy3.11
```

Das betrifft sowohl die Frage beziehungsweise den Default in `copier.yml` als
auch alle Stellen im Workflow-Template, die aus dieser Antwort erzeugt werden.
Die unterstützten PyPy-Versionen sollten nicht unabhängig voneinander an
mehreren Stellen fest eingetragen sein.

## 4. Python-Architektur an den GitHub-Runner anpassen

Die Composite Action erzwingt derzeit für `actions/setup-python` die
Architektur `x64`. `macos-latest` läuft jedoch auf ARM64. Dadurch lädt die
Action eine inkompatible Intel-Python-Version, die unter anderem wegen
fehlender x64-Homebrew-Bibliotheken nicht startet.

Die Architektur sollte vom Runner übernommen werden:

```yaml
- name: Set up Python
  uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b
  with:
    python-version: ${{inputs.python-version}}
    architecture: ${{runner.arch == 'ARM64' && 'arm64' || 'x64'}}
    allow-prereleases: true
```

Noch besser ist es, `architecture` wegzulassen, sofern `setup-python` dann auf
allen vorgesehenen Runnern zuverlässig die native Architektur auswählt.

## 5. macOS-Runner nicht auf eine veraltete Plattform festlegen

Die Matrix sollte `macos-latest` statt `macos-14` verwenden, sofern das
Template nicht gezielt eine bestimmte macOS-Version testen muss:

```yaml
os: [ubuntu-latest, windows-latest, macos-latest]
```

Alle zugehörigen `exclude`-Einträge müssen denselben Labelwert verwenden.
Diese Änderung allein reicht jedoch nicht aus; die Composite Action muss auch
die native Runner-Architektur gemäß Abschnitt 4 berücksichtigen.

## 6. Generierte Kombinationen als Template-Test prüfen

Das Template sollte mindestens ein generiertes Beispielprojekt in CI erzeugen
und dessen Workflow-Konfiguration statisch prüfen. Sinnvolle Prüfungen sind:

- `actionlint` für alle generierten Workflows,
- Konsistenz zwischen `data_file = "$TOP/.coverage"` und den Job-Umgebungen,
- keine Kombination aus `coverage run` und `pytest -n` ohne
  Unterprozesskonfiguration,
- native Architektur für ARM64-macOS,
- eine tatsächlich installierbare PyPy-Version,
- `uv lock --check` beziehungsweise `uv run --locked`,
- ein Testlauf mit der niedrigsten direkten Auflösung.

Zusätzlich sollte ein durch Copier erzeugtes Smoke-Projekt regelmäßig auf
Ubuntu, Windows, macOS und PyPy ausgeführt werden. Eine reine YAML-Prüfung kann
Architektur- und Wheel-Kompatibilitätsprobleme nicht erkennen.

## Akzeptanzkriterien

Nach den Template-Änderungen sollte ein frisch erzeugtes Projekt ohne manuelle
Nacharbeit folgende GitHub-Actions-Jobs erfolgreich ausführen:

- alle konfigurierten CPython-Versionen auf Ubuntu,
- die älteste und neueste CPython-Version auf Windows und macOS,
- PyPy 3.11 auf Ubuntu,
- `lowest-direct` für die älteste und neueste CPython-Version,
- Zusammenführen und Prüfen der Coverage-Daten,
- alle Pre-Commit- und `actionlint`-Prüfungen.

Die entsprechenden, in Matchify bereits bewährten Änderungen befinden sich in
den Commits `96538b5`, `d2e8d59` und `52ae891` des Copier-Update-Branches.
