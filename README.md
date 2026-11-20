# Aya — Komara Agency

Assistante conversationnelle de Komara Agency, en application web autonome.
Plus de Telegram : Aya tourne comme un serveur web et s'installe sur ordinateur
et sur téléphone, comme une application classique (PWA).

## Ce que fait Aya

- Répond avec les fiches de `aya_seed.py` (ton d'Aya, tes prix, tunnel de vente,
  objections) : correspondance sur les questions, aucune IA ni API, la réponse
  est exactement celle écrite dans le seed. `knowledge_base/` et les
  informations ajoutées depuis `/admin` complètent ce que le seed ne couvre pas.
- Affiche une galerie du portfolio (`web/static/portfolio/`).
- Reconnaît les salutations et les adieux, et bloque les tentatives
  d'extraction de prompt.
- Guide le client dans un parcours de devis (service, budget, confirmation),
  puis enregistre la demande : elle est consultable sur `/api/quotes`.
- Garde l'historique de chaque conversation dans une base locale SQLite.

## Installation sur ordinateur

```bash
git clone https://github.com/ndinekomara-web/Komara-Agency-Aya-2.git
cd Komara-Agency-Aya-2
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Ouvrez ensuite `http://localhost:8000`.

## Installation sur téléphone (et sur ordinateur) comme une application

L'application est une PWA : elle s'installe depuis le navigateur, sans store.

1. Mettez Aya en ligne, ou lancez-la sur un ordinateur du même réseau.
2. Ouvrez l'adresse dans le navigateur du téléphone : `http://IP-DU-PC:8000`.
3. **Android / Chrome** : menu ⋮ → « Installer l'application ».
4. **iPhone / Safari** : bouton Partager → « Sur l'écran d'accueil ».
5. **Ordinateur / Chrome ou Edge** : icône d'installation dans la barre d'adresse.

Aya s'ouvre alors en plein écran, avec son icône, comme ChatGPT.

> Une PWA exige HTTPS pour s'installer proprement en dehors de `localhost`.
> En production, mettez Aya derrière un domaine avec certificat (Railway,
> Render, ou un reverse proxy Caddy/Nginx sur votre serveur).

## Déploiement

### Docker (recommandé sur un VPS)

```bash
cp .env.example .env
docker compose up -d --build
```

Aya écoute sur le port 8000. Les conversations sont conservées dans `./data`.

### Railway

Le dépôt est prêt : `railway.json` fixe la commande de démarrage et la sonde
de santé (`/api/health`).

1. Sur [railway.app](https://railway.app), **New Project → Deploy from GitHub repo**,
   puis choisissez `Komara-Agency-Aya-Web`.

   > La commande de démarrage est `python app.py` : l'application lit elle-même
   > la variable `PORT`. N'utilisez pas `uvicorn --port $PORT` dans Railway,
   > qui passe la valeur littérale et provoque
   > `Invalid value for '--port'`.
2. **Settings → Networking → Generate Domain** : vous obtenez une adresse HTTPS.
   C'est celle que le téléphone ouvrira.
3. **Variables** (Settings → Variables) :

   | Variable | Valeur conseillée |
   | --- | --- |
   | `APP_ACCESS_TOKEN` | un mot de passe de votre choix (protège la conversation) |
   | `RAG_BACKEND` | `keyword` (léger) ou `embed` (plus fin, plus lourd) |
   | `DEFAULT_LANGUAGE` | `fr` |

   `PORT` est fourni automatiquement par Railway : ne le définissez pas.
4. **PostgreSQL** (recommandé) : *New → Database → Add PostgreSQL* dans le
   même projet. Railway crée la variable `DATABASE_URL`, et Aya s'y connecte
   toute seule : l'historique survit aux redéploiements.
5. Déployez, puis ouvrez l'adresse HTTPS sur le téléphone et installez
   l'application.

Le port est lu depuis `$PORT`. Sans PostgreSQL, Aya écrit dans un fichier
SQLite (`/app/data` en production, `./data` en local) : cela fonctionne, mais
le fichier est perdu à chaque déploiement.

## Base de données

| Situation | Base utilisée |
| --- | --- |
| `DATABASE_URL` défini (Railway, Render, Supabase…) | PostgreSQL |
| `DATABASE_URL` vide (local, VPS) | SQLite dans `MEMORY_DIR` |

Le schéma est créé automatiquement au démarrage (`sessions`, `messages`).
La connexion PostgreSQL réessaie plusieurs fois si la base démarre après
l'application, et force `sslmode=require` si le paramètre est absent.

Pour vérifier la base active :

```bash
curl https://votre-domaine/api/health
```

## Configuration

Toutes les options passent par des variables d'environnement (voir `.env.example`).

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `PORT` | Port d'écoute | `8000` |
| `DEFAULT_LANGUAGE` | Langue de départ | `fr` |
| `APP_ACCESS_TOKEN` | Mot de passe protégeant la conversation | vide (public) |
| `ADMIN_ID` | IP(s) autorisées pour `/admin`, séparées par des virgules | vide (désactivé) |
| `RAG_BACKEND` | `auto`, `keyword` ou `embed` | `auto` |
| `DATABASE_URL` | Connexion PostgreSQL (sinon SQLite) | vide |
| `MEMORY_DIR` | Dossier de la base SQLite | `./data` |
| `GOOGLE_SHEETS_ID` | Journal Sheets (facultatif) | vide |

### Deux moteurs de recherche

- **Mots-clés** (défaut) : aucune dépendance lourde, démarrage instantané.
- **Embeddings** : `pip install -r requirements-embeddings.txt`, puis
  `RAG_BACKEND=embed`. Meilleure compréhension, mais télécharge un modèle
  d'environ 120 Mo au premier lancement.

En mode `auto`, Aya utilise les embeddings s'ils sont installés et bascule
sinon sur les mots-clés : l'application ne tombe jamais en panne à cause
d'une dépendance manquante.

## Interface

Messagerie façon WhatsApp : horodatage des messages, séparateurs de jour,
appui long sur un message pour le copier, panneau *Réglages* (langue,
installation, vider la conversation, lien d'administration).

Les icônes viennent de l'affiche officielle (`web/static/icons/logo-aya.png`,
`icon-192-v3.png`, `icon-512-v3.png`, `icon-maskable-512-v3.png`). Pour changer
d'affiche, remplacez ces fichiers en gardant les mêmes noms, puis incrémentez
`VERSION` dans `web/service-worker.js`.

## Administration par IP (`/admin`)

Une page d'administration permet d'ajouter des connaissances sans toucher au
code. Elle est réservée aux adresses IP listées dans `ADMIN_ID`.

1. Définissez `ADMIN_ID` dans Railway (ex. `ADMIN_ID=41.140.12.34`).
2. Ouvrez `/admin` depuis cette adresse.
3. Saisissez la langue, le sujet et l'information, puis *Enregistrer*.
   Aya l'utilise immédiatement.

Les informations sont stockées en base (`knowledge_entries`), donc elles
survivent aux redéploiements. Si l'IP n'est pas autorisée, la page affiche
l'IP détectée : il suffit de la recopier dans `ADMIN_ID`.

> L'IP d'un téléphone mobile change (4G, Wi-Fi, opérateur). En cas de refus,
> rouvrez `/admin` pour lire la nouvelle IP et mettez-la à jour.

## Modifier les réponses d'Aya

Tout se joue dans `aya_seed.py` : une fiche est `(["question 1", "question 2"], "réponse")`.

- *Prix et contact* : variables d'environnement `PRICE_LOGO`, `PRICE_AFFICHE`,
  `PRICE_SITE`, `PRICE_RETOUCHE`, `PRICE_PACK_PREMIUM`, `KOMARA_WHATSAPP`.
  Pas besoin de toucher au code.
- *Ajouter une réponse sans redéployer* : page `/admin` (stockée en base).
- *Portfolio* : déposez une image dans `web/static/portfolio/`, légende dans `captions.json`.

Ordre de réponse : seed, puis connaissances `/admin`, puis `knowledge_base/`.

## Enrichir les connaissances

Les réponses viennent de fichiers Markdown versionnés, un dossier par langue :

```
knowledge_base/
├── fr/   (services.md, tarifs.md, faq.md)
├── en/
└── ar/
```

Ajoutez ou modifiez un fichier, puis redémarrez l'application. Les titres
`##` délimitent les sections ; un titre clair améliore nettement la recherche.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Structure

| Fichier | Rôle |
| --- | --- |
| `app.py` | Serveur web FastAPI et API de conversation |
| `web/` | Interface (HTML, CSS, JS), manifeste et service worker PWA |
| `message_router.py` | Enchaînement des traitements d'un message |
| `rag_engine.py` | Recherche dans la base de connaissances |
| `logical_steps.py` | Parcours de devis |
| `db.py` | Connexion PostgreSQL / SQLite |
| `chat_store.py` | Historique des conversations et demandes de devis |
| `memory_sheets.py` | Journal Google Sheets (facultatif) |

## Licence

© Komara Agency. Tous droits réservés.
