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
2. Ouvrez l'adresse affichée dans le navigateur du téléphone.
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
3. **Réglages** : les options se règlent dans les variables d'environnement
   de la plateforme d'hébergement. Elles ne sont volontairement pas listées ici.
4. **PostgreSQL** (recommandé) : *New → Database → Add PostgreSQL* dans le
   même projet. La connexion est fournie par la plateforme : l'historique
   survit aux redéploiements.
5. Déployez, puis ouvrez l'adresse HTTPS sur le téléphone et installez
   l'application.

Le port est lu depuis `$PORT`. Sans PostgreSQL, Aya écrit dans un fichier
SQLite (`/app/data` en production, `./data` en local) : cela fonctionne, mais
le fichier est perdu à chaque déploiement.

## Base de données

| Situation | Base utilisée |
| --- | --- |
| Base PostgreSQL fournie par l'hébergement | PostgreSQL |
| Aucune base configurée (local, VPS) | SQLite dans le dossier de données |

Le schéma est créé automatiquement au démarrage (`sessions`, `messages`).
La connexion PostgreSQL réessaie plusieurs fois si la base démarre après
l'application, et force `sslmode=require` si le paramètre est absent.

Pour vérifier la base active :

```bash
curl https://votre-domaine/api/health
```

## Configuration

Les options se règlent uniquement par variables d'environnement, côté
hébergement. Ce dépôt ne documente ni leurs noms ni leurs valeurs : il reste
lisible publiquement sans rien exposer.

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

## Ce que fait Aya

Messagerie, réponses du seed, moteur tolérant aux fautes, parcours de devis,
photos reçues, alertes, facture PDF, statistiques, exports, anti-spam.
Le détail des routes est dans `/docs` (FastAPI) une fois le service lancé.

## Reranker (pertinence des réponses)

`reranker.py` relit chaque réponse candidate avant de l'envoyer.

- Moteur par défaut : **lexical pondéré**, sans aucune dépendance (IDF sur les
  questions du seed, trigrammes pour les fautes et le langage SMS, synonymes
  bot/robot/chatbot, bonus de phrase exacte). Score dans [0, 1].
- Si `sentence_transformers` est installé, le cross-encoder ms-marco prend le
  relais automatiquement (meilleur, mais ~2 Go : inutile sur Railway).
- En dessous du seuil de pertinence, Aya ne
  répond pas une fiche au hasard : elle demande de reformuler.

Le moteur et le seuil se règlent côté hébergement.

## Prix officiels

Les prix suivent la grille du site officiel (komaraagency.github.io/komara-agency-site) :

| Offre | Prix |
| --- | --- |
| Logo seul | 50 € |
| Pack Premium (logo + identité) | 150 € |
| Affiche / visuel | 30 € |
| Site vitrine | 250 € |
| Retouche photo | 10 € |
| Bot Telegram scripté | 50 € |
| Bot WhatsApp vendeur | 100 € |
| Agent IA Premium | 150 € |
| Maintenance mensuelle | 50 €/mois |

Express 24h : +30 %. Paiement : 50 % pour démarrer, 50 % à la livraison.

## Catalogue et panier

`catalogue.py` reprend les offres officielles (Bot Scripté 50 €, Chatbot IA
Vendeur 100 €, Agent IA Premium 150 €, Maintenance 50 €). Dans la
conversation : *catalogue*, *ajoute 2*, *panier*, *commander*, *vider*.
La commande suit trois questions (nom, livraison, confirmation) puis est
enregistrée, une alerte est créée et le panier est vidé.

Les questions de prix (« tarifs », « prix ») restent servies par le seed :
c'est la grille design, distincte du catalogue.

## Administration (`/admin`)

Une page d'administration permet d'ajouter des connaissances, de suivre les
devis et les commandes, sans toucher au code. L'accès est restreint côté
serveur (adresse autorisée configurée dans l'hébergement).

Les informations sont stockées en base (`knowledge_entries`), donc elles
survivent aux redéploiements.

## Modifier les réponses d'Aya

Tout se joue dans `aya_seed.py` : une fiche est `(["question 1", "question 2"], "réponse")`.

- *Prix et contact* : réglés côté hébergement, sans toucher au code. Aucun
  tarif ni numéro n'est écrit dans ce dépôt.
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
