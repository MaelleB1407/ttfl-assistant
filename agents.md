# Agents & Bonnes Pratiques Python

## Objectif
- Synthétiser les standards Python à rappeler à un agent IA pour garantir un code propre, testé et sécurisé.
- Servir de checklist lors de la rédaction des prompts et de la revue des modifications proposées.

## Style & Qualité de Code
- **PEP 8 / Ruff**: exiger un code compatible PEP 8, compatible avec `ruff` et formatable via `black`.
- **Typing**: demander du typage statique (`from __future__ import annotations`, types précis, `TypedDict`/`Protocol` si utile) et prévoir un passage `mypy`.
- **Docstrings**: préférer des docstrings concises au format Google ou NumPy pour les fonctions publiques.
- **Nomage**: imposer des noms explicites (`snake_case` pour fonctions/variables, `CamelCase` pour classes) et limiter les abréviations.
- **Import**: privilégier les imports standards (stdlib, puis externes, puis internes) en ordre alphabétique et supprimer l’inutile.

## Architecture & Structure
- Séparer logique métier, accès aux données et interfaces; éviter les scripts monolithiques.
- Favoriser les fonctions pures et la paramétrisation (éviter les variables globales, préférer les dataclasses/config).
- Pour l’ETL, isoler les étapes extract → transform → load en fonctions testables.
- Documenter les effets de bord (I/O, requêtes HTTP, écriture DB) dans les docstrings ou commentaires ciblés.

## Dépendances & Config
- Référencer `requirements.txt`/`pyproject.toml` et demander l’ajout de dépendances uniquement si nécessaire.
- Préférer les variables d’environnement pour les secrets (`os.getenv`, `pydantic-settings`).
- Lorsque l’agent propose une lib, exiger justification (licence, popularité, maintenance).

## Tests & Validation
- **Unit tests**: demander systématiquement un test `pytest` pour toute logique nouvelle ou bugfix.
- **Données**: isoler les fixtures (fichiers tests, snapshots) et éviter les dépendances sur des services externes pour les tests rapides.
- **CI locale**: rappeler de lancer `pytest`, `ruff`, `black --check`, `mypy` après modifications.
- **Cas limites**: questionner l’agent sur les edge cases (données vides, erreurs réseau, timeouts, fuseaux horaires).

## Observabilité & Gestion d’erreurs
- Utiliser `logging` plutôt que `print`; configurer un logger par module.
- Propager des exceptions explicites (`ValueError`, `RuntimeError`, exceptions custom) avec messages utiles.
- Ajouter des garde-fous (`if not data: return []`) pour éviter les crashs silencieux.

## Sécurité & Données
- Ne jamais hardcoder de secrets, clés API ou mots de passe.
- Valider les entrées utilisateur/externes (schemas `pydantic`, `dataclasses` + validation).
- Pour SQL, imposer l’usage de paramètres préparés (psycopg `execute` avec variables).
- Anonymiser ou synthétiser les exemples de données avant de les partager à l’agent.

## Workflow avec l’Agent
- Définir le fichier cible, la fonctionnalité attendue et les contraintes de style dès le prompt initial.
- Demander explicitement le diff attendu, la liste des fichiers modifiés et les commandes de tests à exécuter.
- Requérir un paragraphe de justification: choix techniques, risque de régression, TODO potentiels.
- Après génération, revoir le code comme pour une PR humaine: `git diff`, tests, lint.
- Consigner dans la PR/commit les tests effectués et mentionner l’usage de l’agent.

## Ressources
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)
- [Typing Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
- [Pytest Best Practices Guide](https://docs.pytest.org/en/stable/goodpractices.html)
- [Ruff Rules](https://docs.astral.sh/ruff/rules/)
