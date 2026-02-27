#!/bin/bash
# ============================================================
# update_artist_photo.sh
# Synchronise les photos d'artistes depuis Railway → GitHub
# Usage: ./update_artist_photo.sh
# ============================================================

set -e  # Stop si erreur

RAILWAY_URL="https://pto-production-9873.up.railway.app"
ARTIST_DIR="frontend/public/songs/images/artist"
INDEX_HTML="frontend/public/index.html"

# ── Couleurs ──────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   PTO — Sync Photos Artistes         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Vérifier qu'on est dans le bon dossier ─────────────
if [ ! -f "requirements.txt" ] || [ ! -d "backend" ]; then
  echo -e "${RED}❌ Lance ce script depuis la racine du repo PTO${NC}"
  echo "   cd ~/PTO && ./update_artist_photo.sh"
  exit 1
fi

# ── 2. Lister les photos disponibles sur Railway ──────────
echo -e "${YELLOW}🔍 Récupération des photos sur Railway...${NC}"

AVAILABLE=$(curl -s "$RAILWAY_URL/debug-files" | python3 -c "
import sys, json
data = json.load(sys.stdin)
files = data.get('artist_files', [])
for f in sorted(files):
    print(f)
" 2>/dev/null)

if [ -z "$AVAILABLE" ]; then
  echo -e "${RED}❌ Impossible de contacter Railway. Vérifie ta connexion.${NC}"
  exit 1
fi

echo ""
echo -e "${GREEN}Photos disponibles sur Railway :${NC}"
echo "$AVAILABLE" | nl -ba
echo ""

# ── 3. Lister les photos déjà en local ────────────────────
LOCAL_FILES=$(ls "$ARTIST_DIR" 2>/dev/null || echo "")

echo -e "${YELLOW}📁 Photos déjà dans le repo local :${NC}"
if [ -z "$LOCAL_FILES" ]; then
  echo "   (aucune)"
else
  echo "$LOCAL_FILES" | sed 's/^/   /'
fi
echo ""

# ── 4. Détecter les nouvelles photos à télécharger ────────
NEW_FILES=""
while IFS= read -r file; do
  if ! echo "$LOCAL_FILES" | grep -qF "$file"; then
    NEW_FILES="$NEW_FILES$file\n"
  fi
done <<< "$AVAILABLE"

if [ -z "$(echo -e "$NEW_FILES" | tr -d '[:space:]')" ]; then
  echo -e "${GREEN}✅ Toutes les photos sont déjà synchronisées !${NC}"
  echo ""
  read -p "Forcer la re-synchronisation de toutes les photos ? (o/N) " FORCE
  if [[ "$FORCE" != "o" && "$FORCE" != "O" ]]; then
    echo "Rien à faire. Au revoir !"
    exit 0
  fi
  NEW_FILES=$(echo "$AVAILABLE")
fi

echo -e "${YELLOW}🆕 Nouvelles photos à télécharger :${NC}"
echo -e "$NEW_FILES" | grep -v '^$' | sed 's/^/   📸 /'
echo ""

read -p "Télécharger et pusher ces photos ? (o/N) " CONFIRM
if [[ "$CONFIRM" != "o" && "$CONFIRM" != "O" ]]; then
  echo "Annulé."
  exit 0
fi

# ── 5. Télécharger chaque nouvelle photo ──────────────────
echo ""
echo -e "${YELLOW}📥 Téléchargement des photos...${NC}"

DOWNLOADED=0
FAILED=0

while IFS= read -r file; do
  [ -z "$file" ] && continue
  
  ENCODED=$(echo "$file" | python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))")
  DEST="$ARTIST_DIR/$file"
  
  echo -n "   Téléchargement : $file ... "
  
  HTTP_CODE=$(curl -s -w "%{http_code}" -o "$DEST" "$RAILWAY_URL/songs/images/artist/$ENCODED")
  
  if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅${NC}"
    DOWNLOADED=$((DOWNLOADED + 1))
  else
    echo -e "${RED}❌ (HTTP $HTTP_CODE)${NC}"
    rm -f "$DEST"
    FAILED=$((FAILED + 1))
  fi
done <<< "$(echo -e "$NEW_FILES")"

echo ""
echo -e "   Téléchargées : ${GREEN}$DOWNLOADED${NC} | Échouées : ${RED}$FAILED${NC}"

# ── 6. Mettre à jour le manifest dans index.html ──────────
echo ""
echo -e "${YELLOW}🔧 Mise à jour du manifest dans index.html...${NC}"

python3 << 'PYEOF'
import os, json, re

d = 'frontend/public/songs/images/artist'
manifest = {}
for f in sorted(os.listdir(d)):
    ext = os.path.splitext(f)[1].lower()
    if ext in ('.jpg', '.jpeg', '.png', '.webp'):
        name = os.path.splitext(f)[0]
        manifest[name] = f

files_list = json.dumps(sorted(manifest.values()), ensure_ascii=False)
manifest_js = json.dumps(manifest, ensure_ascii=False)

with open('frontend/public/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Mettre à jour artistFiles
content = re.sub(
    r'const artistFiles = \[.*?\];',
    f'const artistFiles = {files_list};',
    content, flags=re.DOTALL
)

# Mettre à jour artistManifest
content = re.sub(
    r'const artistManifest = \{\};',
    'const artistManifest = {};',
    content
)

with open('frontend/public/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"   ✅ {len(manifest)} artistes dans le manifest")
for name, file in sorted(manifest.items()):
    print(f"   · {name} → {file}")
PYEOF

# ── 7. Git add + commit + push ────────────────────────────
echo ""
echo -e "${YELLOW}🚀 Push sur GitHub...${NC}"

git add "$ARTIST_DIR/" "$INDEX_HTML"

# Vérifier s'il y a quelque chose à commiter
if git diff --cached --quiet; then
  echo -e "${GREEN}✅ Rien de nouveau à commiter (déjà à jour)${NC}"
else
  COMMIT_MSG="feat: sync photos artistes ($(date '+%Y-%m-%d %H:%M'))"
  git commit -m "$COMMIT_MSG"
  git push origin main
  echo -e "${GREEN}✅ Photos synchronisées et pushées !${NC}"
fi

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ Synchronisation terminée !      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "🌐 Site : ${GREEN}https://pto-production-9873.up.railway.app${NC}"
echo ""
