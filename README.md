# AI factory

Webhook GitHub uruchamia zadanie po dodaniu etykiety `ai` do issue. Worker klonuje repozytorium do osobnego wolumenu Docker, instaluje zależności z manifestów w jego katalogu głównym i uruchamia CLI Claude Code oraz Codex w kontenerze. Claude zmienia kod aplikacji, Codex przegląda zmiany, tworzy testy zachowania i uruchamia je. Gdy Codex zwróci `VERDICT: PASS`, worker wypycha gałąź, tworzy pull request i dodaje link w komentarzu issue. Błąd oraz ostatnia odpowiedź agenta trafiają do tego samego issue przez `mark_problem_on_gh`.

## Przygotowanie

1. Skopiuj `.env.example` do `.env`. Ustaw `GH_SECRET` jako sekret webhooka, `GITHUB_TOKEN` jako token GitHub z uprawnieniami do odczytu i zapisu zawartości repozytorium, pull requestów i komentarzy issue, oraz `CLAUDE_SETUP_TOKEN` wygenerowany przez `claude setup-token`. `GH_SECRET` nie jest tokenem GitHub API.
2. Zaloguj Codex CLI przez `codex login` i upewnij się, że `$HOME/.codex/auth.json` istnieje. Fabryka korzysta z sesji CLI, bez klucza OpenAI API. W kontenerze API plik jest montowany tylko do odczytu, a worker kopiuje go do kontenera zadania wyłącznie na czas pracy Codex.
3. Zapewnij workerowi dostęp do skonfigurowanego demona Docker. Zalecany jest osobny, rootless Docker i ustawienie `DOCKER_HOST` na jego endpoint. Worker działa na hoście, dzięki czemu kontener API nie dostaje dostępu do demona. W tej konfiguracji WSL `docker version` zgłasza brak integracji Docker Desktop, więc najpierw trzeba uruchomić dostępny endpoint Docker.
4. Zbuduj obraz zadania: `docker build -f Dockerfile.runtime -t factory-runtime:local .`.
5. Uruchom API i Redis: `docker compose up --build -d`.
6. Uruchom worker na hoście z tym samym kodem: `python3 -m venv venv && venv/bin/pip install -r requirements.in`, następnie `REDIS_URL=redis://localhost:6379/0 CODEX_AUTH_PATH="$HOME/.codex/auth.json" venv/bin/taskiq worker src.broker:broker src.processing --workers 1 --max-async-tasks 1`. Użyj istniejącego środowiska `venv`, jeśli jest już przygotowane.
7. Skonfiguruj webhook GitHub na `POST /github` dla zdarzeń Issues z typem zawartości `application/json`. Dodanie etykiety `ai` uruchamia zadanie.

Obraz zadania zawiera Python, Node.js, Go, Rust, Javę i oba CLI. Instalator obsługuje w katalogu głównym `requirements.txt`, `requirements.in`, `pyproject.toml`, `package.json`, `go.mod` oraz `Cargo.toml`. Jeśli manifestu nie ma, agenci używają obrazu bazowego i mogą instalować brakujące pakiety w przestrzeni użytkownika. Narzędzia systemowe można dodać do `Dockerfile.runtime`.

`CLAUDE_MODEL=opus` wybiera rodzinę Opus przez alias CLI. `LOOP_LIMIT` określa maksymalną liczbę tur agentów i musi być parzystą liczbą od 2 do 8. Jedna para tur to implementacja Claude i przegląd Codex. Codex uruchamia własny harness bez jego wewnętrznej piaskownicy, ponieważ cały proces działa jako użytkownik bez uprawnień w ograniczonym kontenerze Docker bez gniazda demona. Kontrola plików zatrzyma zadanie, jeśli Claude zapisze test albo Codex zapisze plik poza testami. Powodzenie wymaga też, by Codex utworzył lub zmienił test.

## Sprawdzenie

`venv/bin/python -m pytest -q` uruchamia testy webhooka, promptów, komentarzy GitHub i przebiegu pracy. [Scenariusze promptów](docs/prompt-smoke.md) opisują ręczną próbę z prawdziwymi CLI i małym repozytorium.

Dokumentacja: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [GitHub issue comments](https://docs.github.com/en/rest/issues/comments), [GitHub pull requests](https://docs.github.com/en/rest/pulls/pulls).
