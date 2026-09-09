# Exercice technique — alternance apowerb

Bienvenue, et merci du temps que vous y consacrez.

Ce dépôt est une **copie figée** d'apowerb, notre plateforme d'agents IA open
source, préparée pour cet exercice. Rien de ce que vous produirez ici ne sera
intégré à notre produit : ce dépôt existe pour cet entretien, et votre travail
reste le vôtre.

## Le signalement

Un utilisateur nous écrit :

> « J'ai un agent qui enchaîne trois sous-agents : le premier extrait les
> données, le deuxième les analyse, le troisième rédige la synthèse. Ça
> fonctionnait.
>
> Hier j'ai corrigé une faute de frappe dans la description du premier
> sous-agent, depuis l'interface. Rien d'autre. Depuis, le deuxième ne reçoit
> plus rien du premier : il travaille dans le vide et sort n'importe quoi.
>
> Le plus déroutant, c'est qu'il n'y a aucune erreur. Tout répond normalement,
> l'exécution se termine, et le résultat est simplement faux. »

## Ce qu'on vous demande

Corrigez le défaut, et ouvrez une pull request **sur votre propre fork**.

- Le correctif tient en moins de 200 lignes modifiées.
- Il est accompagné d'un test qui échoue avant la correction et passe après.
- La description de la PR contient trois choses : ce que vous avez changé,
  **comment vous avez établi la cause** (vos hypothèses successives, y compris
  celles que vous avez abandonnées et pourquoi), et **ce que vous avez vérifié,
  avec la commande et sa sortie**.
- Dites aussi ce que vous n'avez pas vérifié. C'est une réponse valable, et une
  réponse que nous lisons.

Deux questions à traiter dans la PR, en quelques lignes chacune :

- Qu'avez-vous choisi de ne pas corriger, et pourquoi ?
- Voyez-vous ailleurs dans le dépôt un endroit qui présente le même défaut ?

## Les outils

L'usage d'un assistant IA est **autorisé et attendu** : nous travaillons tous
avec. Indiquez simplement dans la PR ce que vous lui avez confié. Ce n'est pas
un piège et cela n'enlève aucun point — nous regardons la façon dont vous le
pilotez, pas le fait de vous en passer.

## Démarrer

Vous n'avez besoin **ni d'une base de données, ni du serveur** : ce défaut se
reproduit et se corrige au niveau des tests unitaires. Ne perdez pas votre
temps à monter la pile complète.

```bash
uv venv --python 3.13
uv sync --group dev

export DB_SCHEMA=""
export ENCRYPT_KEY="qFJ2xY8vT6mN4pR9sL3wK7hG5bC1dZ0aE2uI8oP6yX4="

uv run pytest -q
```

Les deux variables ne sont pas décoratives, et sans elles vous verrez des
dizaines d'échecs qui n'ont rien à voir avec l'exercice :

- `DB_SCHEMA=""` — les modèles qualifient leurs tables avec
  `settings.db_schema` et SQLite n'a pas de schémas ; c'est ce qui permet à la
  suite de tourner sans PostgreSQL.
- `ENCRYPT_KEY` — clé de chiffrement des secrets d'intégration. Celle
  ci-dessus est une clé jetable, générée pour cet exercice et sans valeur.

## À quoi ressemble une suite « normale » ici

Même sans aucune modification de votre part, **une quinzaine de tests échouent
et une quarantaine d'autres ne peuvent pas démarrer** : ils attendent une vraie
base de données ou un service externe que cette copie n'a pas. C'est le point de
départ, pas votre travail.

Ne cherchez donc pas le vert complet. Votre repère, c'est **votre** test : il
doit échouer avant votre correction et passer après. Le reste ne doit pas
bouger.

## Conventions

- Branche nommée `<type>/<slug>`, par exemple `fix/mon-correctif`.
- Messages de commit au format [Conventional Commits](https://www.conventionalcommits.org/) :
  `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`. Sujet en anglais,
  en minuscules, sans point final.
- `ruff check .` et `ruff format .` avant de pousser.
- Tout est annoté en types ; n'ajoutez pas de dépendance.

## Le cadre

Comptez environ **trois heures**. Vous avez **cinq jours** pour rendre.

Si vous butez, envoyez ce que vous avez avec la description de là où vous en
êtes : une PR incomplète mais lucide vaut mieux qu'une PR silencieuse.
