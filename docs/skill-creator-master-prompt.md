# MASTER PROMPT — AgentBox `skill-creator`

**Projekt:** AgentBox Skill Creator  
**Target:** `skill-creator`  
**Platforma:** AgentBox v5.x  
**Tryb:** IMPLEMENT → VALIDATE → TEST → INTEGRATE → REPORT

## MISJA

Pracujesz bezpośrednio na platformie AgentBox. Samodzielnie zaprojektuj, utwórz, wdroż, przetestuj i zintegruj profesjonalną umiejętność `skill-creator`.

Ma ona tworzyć, rozwijać, walidować, testować, wersjonować i przygotowywać do dystrybucji nowe Agent Skills dla ChatGPT i Codex.

Docelowe wywołania:

```text
ChatGPT: @skill-creator
Codex:   $skill-creator
Codex:   /skills
```

Nie zakładaj, że samo utworzenie `SKILL.md` na serwerze rejestruje skill w ChatGPT. Rozróżniaj standalone, REPO, USER, ADMIN, SYSTEM i plugin. Nie deklaruj sukcesu integracji bez technicznej weryfikacji.

## ŚRODOWISKO I PREFLIGHT

```text
Host: AgentBox
Tailscale IP: 100.123.66.15
SSH: 22
User: box
Hostname: cursor
Root: /workspace/agentbox-v5
```

Najpierw wykonaj:

```bash
whoami
hostname
pwd
uname -a
python3 --version
git --version
command -v codex && codex --version || true
command -v agent5 && agent5 --version || true
command -v agentbox && agentbox --version || true
command -v tailscale && tailscale status || true
```

Deployment jest dozwolony tylko, gdy użytkownik to `box`, hostname to `cursor`, a root AgentBox to `/workspace/agentbox-v5`. W przeciwnym razie STOP i diagnostyka.

Nie zapisuj haseł, tokenów, API keys ani SSH private keys w kodzie, skillach, logach i artifacts.

## ŹRÓDŁA PRAWDY

Przed implementacją zweryfikuj aktualny format na podstawie:
1. aktualnej oficjalnej dokumentacji OpenAI/ChatGPT/Codex,
2. Agent Skills specification,
3. istniejących systemowych skills,
4. oficjalnych przykładów.

Jeśli standard różni się od założeń tego promptu, zastosuj aktualny standard i opisz różnicę w raporcie.

## INSPEKCJA ISTNIEJĄCYCH SKILLS

Sprawdź:

```text
$HOME/.agents/skills
$PWD/.agents/skills
$REPO_ROOT/.agents/skills
/etc/codex/skills
$HOME/.codex/config.toml
```

Jeżeli istnieje `skill-creator`, ustal jego scope, path, origin, zawartość i dependencies. Nie nadpisuj systemowego/bundled skilla. Nie merge'uj automatycznie skills o tej samej nazwie.

## DOCELOWA STRUKTURA

Zbuduj modularnie:

```text
skill-creator/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── create_skill.py
│   ├── validate_skill.py
│   ├── inspect_skill.py
│   ├── test_skill.py
│   ├── package_skill.py
│   └── doctor.py
├── references/
│   ├── skill-format.md
│   ├── authoring-guide.md
│   ├── progressive-disclosure.md
│   ├── invocation.md
│   ├── metadata.md
│   ├── validation.md
│   ├── testing.md
│   ├── distribution.md
│   ├── security.md
│   └── examples.md
├── templates/
│   ├── instruction-only/
│   ├── scripted/
│   ├── tool-aware/
│   └── plugin-ready/
├── schemas/
│   ├── skill.schema.json
│   └── openai-yaml.schema.json
└── tests/
    ├── test_validator.py
    ├── test_creator.py
    ├── test_metadata.py
    └── fixtures/
```

Dostosuj strukturę, jeśli aktualny standard tego wymaga.

## SKILL.md I PROGRESSIVE DISCLOSURE

`SKILL.md` musi zawierać poprawny frontmatter z `name` i `description`.

```md
---
name: skill-creator
description: ...
---
```

Description ma jasno i zwięźle określać co skill robi, kiedy powinien się aktywować i kiedy nie. Front-load trigger words. Zakres: create, design, update, validate, test, package, improve Agent Skills.

Nie przeładowuj `SKILL.md`. Szczegółową dokumentację przenoś do `references/`, deterministyczną logikę do `scripts/`, szablony do `templates/` lub `assets/`.

## WORKFLOW SKILL-CREATOR

```text
INTENT
→ REQUIREMENTS
→ SCOPE
→ TRIGGERS
→ STRUCTURE
→ GENERATION
→ VALIDATION
→ TEST
→ INSTALL/DISTRIBUTION
→ REPORT
```

Jeżeli wymagania są wystarczające, działaj bez zbędnych pytań. Pytaj tylko o brakujące informacje krytyczne.

Automatycznie rozpoznawaj operacje:

```text
CREATE
UPDATE
VALIDATE
INSPECT
PACKAGE
TEST
```

## TRYBY

Obsługuj:
- instruction-only,
- instruction + references,
- scripted,
- full,
- plugin-ready.

## SCOPES

Obsługuj:

```text
REPO   -> $REPO_ROOT/.agents/skills/<name>
USER   -> $HOME/.agents/skills/<name>
ADMIN  -> /etc/codex/skills/<name>
PLUGIN -> package/distribution
```

Nie modyfikuj SYSTEM bundled skills. Dla prywatnego uniwersalnego skilla preferuj USER; dla repo-specific REPO.

## NAZWY I DESCRIPTION ENGINE

Nazwy: `kebab-case`.

Validator ma odrzucać niepoprawne/problemowe nazwy.

Description musi być krótkie, jednoznaczne, front-loaded i zawierać granice odpowiedzialności. Ostrzegaj przed ogólnikami typu `Helps with development.`

## agents/openai.yaml

Jeżeli aktualny format wspiera ten plik, utwórz poprawne metadane UI i invocation policy. Preferowane dane:

```yaml
interface:
  display_name: "Skill Creator"
  short_description: "Create, validate, test, improve, and package Agent Skills."
  brand_color: "#3B82F6"
  default_prompt: "Create a new reusable Agent Skill from my requirements."

policy:
  allow_implicit_invocation: true
```

Nie deklaruj nieistniejących dependencies.

## INVOCATION

Docelowo skill ma być dostępny przez `@skill-creator` w ChatGPT oraz `$skill-creator`/`/skills` w Codex tam, gdzie host to obsługuje.

Nie implementuj własnego parsera `@`. Za picker odpowiada host.

Implicit matching powinien obejmować m.in.:
- „stwórz nowy skill”,
- „zbuduj umiejętność”,
- „create an agent skill”,
- „napraw SKILL.md”,
- „validate this skill”.

Nie powinien aktywować się dla zwykłego programowania.

## GENERATOR

`create_skill.py` ma:
1. walidować nazwę,
2. wykrywać collision,
3. tworzyć katalog tymczasowy,
4. generować strukturę,
5. uruchamiać validator/test,
6. wykonywać atomic move,
7. raportować wynik.

CLI ma wspierać co najmniej:

```bash
python scripts/create_skill.py   --name ssh-doctor   --description "..."   --scope user   --mode scripted
```

Dodaj `--dry-run`. Nie nadpisuj istniejącego skilla bez jawnego trybu aktualizacji/force, a przed zmianą zawsze twórz backup.

## VALIDATOR

`validate_skill.py` sprawdza:
- katalog,
- `SKILL.md`,
- frontmatter,
- name,
- description,
- format nazwy,
- duplicate names,
- broken references,
- missing scripts,
- YAML/openai.yaml,
- niebezpieczne absolute paths,
- oczywiste embedded secrets.

Wynik:

```text
PASS
WARN
FAIL
```

z poprawnym exit code. Nie wypisuj wartości wykrytych sekretów.

## INSPECT / TEST / DOCTOR

`inspect_skill.py` raportuje Name, Description, Scope, Files, Scripts, References, Assets, Metadata, Dependencies, Warnings i invocation behavior.

`test_skill.py` sprawdza structure, metadata, description, references, scripts oraz SHOULD TRIGGER / SHOULD NOT TRIGGER.

`doctor.py` sprawdza Python, Codex, skill locations, permissions, config.toml, duplicate names, broken skills i opcjonalne plugin tooling.

## BACKUP, ATOMICITY, ROLLBACK

Backupy przechowuj bezpiecznie, np.:

```text
~/.local/share/agentbox/skill-backups/
```

Rejestruj timestamp, hash i change summary. Jeżeli repo używa Git, wykorzystaj historię Git.

Nie zostawiaj częściowo utworzonego skilla. Generuj w temp, waliduj, testuj i dopiero potem atomic move. Przy nieudanej aktualizacji przywróć poprzednią wersję.

## SECURITY

Nigdy nie osadzaj:
- passwords,
- API keys,
- tokens,
- cookies,
- session secrets,
- SSH private keys.

Wygenerowane scripts nie powinny automatycznie wykonywać `sudo`, `rm -rf`, force push ani `curl | sh` bez jawnej potrzeby, policy i approval.

## IMPROVE EXISTING SKILL

Pipeline:

```text
DISCOVER
→ INSPECT
→ VALIDATE
→ IDENTIFY ISSUES
→ BACKUP
→ MODIFY
→ TEST
→ DIFF
→ APPROVE
```

## PLUGIN-READY

Jeżeli szersza dostępność w ChatGPT wymaga plugin packaging, przygotuj skill do dystrybucji jako plugin zgodnie z aktualną specyfikacją.

```text
skill
→ validate
→ package
→ plugin metadata/manifest
→ validation
→ installation/distribution path
```

Jeżeli dostępny jest oficjalny plugin creator, przygotuj kompatybilne wejście zamiast bez potrzeby duplikować cały subsystem.

Nie zakładaj, że lokalny USER skill wystarcza do pojawienia się w pickerze ChatGPT.

## TEMPLATES I FIXTURES

Przygotuj templates:
- instruction-only,
- scripted,
- tool-aware,
- plugin-ready.

Fixtures:
- hello-skill,
- repo-doctor,
- ssh-health-check.

Fixtures trzymaj w testach i nie zaśmiecaj production registry.

## AGENTBOX INTEGRATION

Jeśli AgentBox ma Tool Registry, Policy Engine, Approval Engine, Artifacts, Memory, Evaluation lub Observability — integruj się z nimi zamiast tworzyć konkurencyjne systemy.

Jeśli istnieje Event Bus, emituj:

```text
skill.creation.started
skill.created
skill.validation.passed
skill.validation.failed
skill.updated
skill.packaged
skill.installation.verified
```

Audit loguje timestamp, operation, skill, scope, result — nigdy secret values.

## ARTIFACTS

Dla operacji tworzenia generuj:

```text
SKILL_CREATION_REPORT.md
```

z name, scope, path, mode, files, validation, tests, warnings i installation status.

## SELF-TEST

Self-test ma wykonać:

```text
create fixture
→ validate
→ inspect
→ test
→ modify
→ backup
→ package
→ cleanup
```

## ACCEPTANCE TESTS

### Creation
Utwórz testowo `repo-doctor` analizujący Git repositories. Validator musi zwrócić PASS.

### Trigger

SHOULD TRIGGER:

```text
Create a new Agent Skill for reviewing Rust code.
Build me a reusable skill for SSH diagnostics.
Validate this SKILL.md.
```

SHOULD NOT TRIGGER:

```text
Fix this Rust function.
What is SSH?
Create a PNG icon.
```

### Collision
Ponowne tworzenie istniejącego skilla ma zakończyć się bezpiecznym STOP/warning bez utraty danych.

### Invalid
Brak description -> FAIL.

### Secret
Podejrzany embedded secret -> WARN/FAIL bez ujawnienia wartości.

### Progressive disclosure
Duże materiały powinny być w references, nie w centralnym SKILL.md.

### Discovery
Oddzielnie zweryfikuj:
A. Codex discovery,
B. ChatGPT desktop discovery, jeśli technicznie dostępne,
C. plugin/distribution path dla ChatGPT.

Nie oznaczaj B/C jako PASS bez rzeczywistej weryfikacji.

## UX

Przykład:

```text
@skill-creator
Stwórz skill AgentBox Backup, który robi backup bazy SQLite i konfiguracji.
```

Creator powinien:
1. zrozumieć intent,
2. zaproponować `agentbox-backup`,
3. dobrać scope,
4. dobrać mode,
5. wygenerować strukturę,
6. wygenerować instrukcje,
7. zwalidować,
8. przetestować,
9. pokazać wynik.

## QUALITY GATES

Przed statusem READY:

```text
structure PASS
metadata PASS
references PASS
scripts PASS
security PASS
trigger tests PASS
```

Statusy:

```text
DRAFT
VALID
READY_LOCAL
PLUGIN_READY
INSTALLED
DISCOVERY_VERIFIED
FAILED
```

Nie używaj `INSTALLED` ani `DISCOVERY_VERIFIED` bez dowodu.

## INSTALACJA

Po testach zainstaluj AgentBox-owned skill w odpowiednim scope, preferencyjnie:

```text
$HOME/.agents/skills/skill-creator/
```

o ile nie powoduje to problematycznej kolizji z systemowym `skill-creator`.

Jeżeli istnieje systemowy skill o tej samej nazwie, nie niszcz go. Ustal zachowanie hosta przy duplikatach i wybierz bezpieczne rozwiązanie.

## CHATGPT `@` PICKER

Docelowo po wpisaniu `@` użytkownik ma móc wybrać `Skill Creator`.

Jeśli wymaga to plugin packaging — przygotuj plugin-ready artefakty.

Jeśli wymaga ręcznej instalacji/akceptacji w ChatGPT — przygotuj wszystko i dokładnie wskaż ten krok.

Nie obchodź mechanizmu instalacji hosta.

## FINAL VERIFICATION

Uruchom:
- validator,
- unit tests,
- selftest,
- doctor,
- discovery test.

Sprawdź:
- SKILL.md,
- frontmatter,
- agents/openai.yaml,
- scripts,
- references,
- templates,
- schemas,
- tests.

## RAPORT KOŃCOWY

Utwórz:

```text
SKILL_CREATOR_IMPLEMENTATION_REPORT.md
```

Raport:
- Environment,
- Installed path,
- Scope,
- Structure,
- Validation results,
- Unit tests,
- Trigger tests,
- Security checks,
- Codex discovery,
- ChatGPT discovery status,
- Plugin packaging status,
- Warnings,
- Rollback instructions,
- Next steps.

## ZASADA PRAWDY

Nie pisz „Skill działa w ChatGPT”, jeśli zweryfikowałeś tylko pliki na Linux.

Rozróżniaj:

```text
FILES CREATED
LOCAL VALIDATION PASSED
CODEX DISCOVERY VERIFIED
PLUGIN READY
CHATGPT INSTALLATION REQUIRED
CHATGPT DISCOVERY VERIFIED
```

## DEFINITION OF DONE

- [ ] preflight PASS
- [ ] deployment guard PASS
- [ ] existing skills inspected
- [ ] no destructive collision
- [ ] skill-creator created
- [ ] SKILL.md valid
- [ ] progressive disclosure implemented
- [ ] scripts implemented
- [ ] references implemented
- [ ] templates implemented
- [ ] validator implemented
- [ ] doctor implemented
- [ ] tests PASS
- [ ] security scan PASS
- [ ] backups supported
- [ ] atomic creation supported
- [ ] rollback supported
- [ ] USER/REPO scope supported
- [ ] Codex discovery tested
- [ ] plugin-ready path supported
- [ ] ChatGPT @ picker integration status established honestly
- [ ] final report generated

# EXECUTION DIRECTIVE

Nie kończ na planie.

Po preflight **IMPLEMENTUJ**.

Twórz katalogi i pliki, uruchamiaj testy, naprawiaj problemy i powtarzaj testy. Nie zatrzymuj się po pierwszym błędzie, jeśli możesz go bezpiecznie naprawić. Nie wykonuj nieodwracalnych operacji bez approval. Nie zmieniaj działających komponentów AgentBox bez potrzeby.

Po zakończeniu pokaż:
1. installed path,
2. pełne `tree`,
3. wyniki testów,
4. status Codex discovery,
5. status ChatGPT `@` discovery,
6. wymagany plugin/install step,
7. ścieżkę raportu.

Nie dostarczaj demonstracji ani samego szkieletu. Dostarcz działający, modularny, walidowany i testowalny `skill-creator`.

**START.**
