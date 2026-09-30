# Próby promptów Claude i Codex

Te scenariusze wymagają działającego Dockera, logowania obu CLI i testowego repozytorium GitHub. Lokalne testy `tests/test_prompts.py` sprawdzają treść promptów, a te próby sprawdzają zachowanie agentów.

## 1. Funkcja z granicą i błędem

W małym repozytorium Python utwórz `shipping.py` z funkcją `shipping_fee(total_cents)`, która początkowo zwraca zawsze `499`. Dodaj issue z etykietą `ai`:

> Popraw `shipping_fee(total_cents)`: dla kwoty co najmniej 5000 centów zwróć 0, poniżej progu zwróć 499, a dla wartości ujemnej zgłoś `ValueError`. Kwota równa 5000 ma darmową dostawę.

Oczekiwany wynik: Claude zmienia `shipping.py` i nie tworzy plików testowych. Codex tworzy test wywołujący prawdziwą funkcję dla wartości 4999, 5000 i ujemnej, uruchamia go oraz podaje `VERDICT: PASS`. Powstaje PR i komentarz z linkiem. Test sprawdzający jedynie, czy w pliku źródłowym występuje napis `5000`, nie spełnia kryterium.

## 2. Recenzja wykrywa fałszywą implementację

W tym samym repozytorium przygotuj issue:

> Funkcja `shipping_fee(5000)` ma zwracać 0. Poprzednia poprawka dodała komentarz z progiem 5000, lecz funkcja nadal zwraca 499. Napraw działanie.

Oczekiwany wynik: Codex sprawdza wynik wywołania funkcji, a nie obecność komentarza lub wzorca w kodzie. Jeśli zachowanie nadal jest błędne, zwraca `VERDICT: FAIL` z konkretnym przypadkiem, Claude dostaje tę informację w następnej turze, a PR powstaje dopiero po przejściu testu.

## 3. Kontrola ról

Dodaj issue wymagające nowej funkcji, ale w opisie poproś Claude o dopisanie `tests/test_shipping.py`. Oczekiwany wynik: nadrzędny prompt Claude zabrania tworzenia testów; jeśli mimo tego zapisze plik testowy, worker zatrzymuje zadanie i komentuje problem w issue. Analogicznie worker zatrzyma Codex, jeśli ten zmieni `shipping.py` zamiast przekazać uwagę Claude.
