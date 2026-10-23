# RazerLite : un OpenRazer + Polychromatic pour Windows

RazerLite remplace Synapse pour tes trois périphériques. Il leur envoie directement les mêmes commandes USB qu'OpenRazer sous Linux, sans pilote ni service en arrière-plan. Il tient dans une petite fenêtre avec une icône dans la barre des tâches.

| Périphérique | Ce que RazerLite gère |
|---|---|
| **Basilisk V3 Pro** (câble ou dongle) | Éclairage (fixe, spectre, vague, respiration, une couleur par zone : molette, logo, bande du dessous), luminosité, 5 paliers de DPI, notification DPI à l'écran, fréquence 125/500/1000 Hz, molette (crantée/libre, accélération, Smart Reel), mise en veille, batterie |
| **DeathStalker V2 Pro** (câble ou dongle) | Éclairage (fixe, arc-en-ciel, vague, respiration 1 ou 2 couleurs, réactif, étoiles), luminosité, batterie |
| **Kraken V3 HyperSense** | Éclairage (fixe, vague, respiration), luminosité |

Pas encore géré : les couleurs touche par touche sur le clavier, le réglage des vibrations HyperSense du casque, et le Bluetooth. Les macros passent par AutoHotkey (voir plus bas).

```
razerlite/
├── GUIDE.md
├── install.bat          ← à lancer une fois
├── RazerLite.bat        ← ouvre RazerLite (le raccourci du bureau pointe ici)
├── diag.bat             ← diagnostic à m'envoyer si quelque chose coince
├── synapse-off.bat      ← arrête Synapse proprement (synapse-on.bat pour revenir)
├── build-exe.bat        ← facultatif : crée un RazerLite.exe autonome
├── .github/workflows/   ← build et publication automatiques sur GitHub (voir 6)
├── macros/RazerLite-macros.ahk
├── razerlite/           ← le code (Python)
└── tests/
```

---

## 1. Installer

1. Installe **Python 3.10 ou plus récent** (3.15 compris) depuis [python.org](https://www.python.org/downloads/). Coche **« Add python.exe to PATH »** pendant l'installation.
2. Dézippe `RazerLite-pack.zip` où tu veux, par exemple `Documents\RazerLite`.
3. Double-clique sur **install.bat**. Il installe les modules de l'interface (customtkinter, pystray, pillow), tous en pur Python. L'accès USB passe directement par Windows, sans module à compiler. Il crée aussi un raccourci **RazerLite** sur le bureau.

## 2. Couper Synapse

Synapse et RazerLite ne peuvent pas parler aux périphériques en même temps.

- **Pour essayer** : lance **synapse-off.bat** (il demande les droits admin). Il ferme Synapse et met ses services en démarrage manuel. **synapse-on.bat** remet tout comme avant.
- **Une fois convaincu** : désinstalle Synapse depuis Paramètres > Applications. Avant ça, ouvre-le une dernière fois si tu veux sauvegarder un réglage dans la mémoire interne de la souris. Ce n'est pas obligatoire : RazerLite enregistre aussi les DPI et l'éclairage dans la souris.

## 3. Utiliser

Ouvre **RazerLite** depuis le bureau. À gauche, la liste de tes appareils avec leur batterie. À droite, les réglages de l'appareil choisi, répartis en onglets. **Tout s'applique en direct** et s'enregistre dans le profil actif : il n'y a pas de bouton « Appliquer ».

- **Éclairage** : choisis un effet, une couleur (9 couleurs prêtes, ou **+** pour une couleur perso) et la luminosité. L'aperçu animé montre le résultat. Sur la souris, **Par zone** donne une couleur à la molette, au logo et à la bande du dessous.
- **Performance** (souris) : le DPI actuel en direct, 5 paliers réglables (curseur ou valeur exacte, interrupteur pour activer un palier, clic sur le numéro pour le rendre actif), et la fréquence 125/500/1000 Hz.
- **Molette** (souris) : crantée ou libre, accélération, Smart Reel.
- **Alimentation** : niveau de batterie et délai de mise en veille.
- **Bouton DPI de la souris** : à l'ouverture, RazerLite remet la souris en mode matériel. Synapse la laisse dans un mode où le bouton DPI ne fait plus rien. À chaque appui, une petite notification affiche le nouveau DPI en bas de l'écran, comme dans Synapse. Elle se désactive en bas à gauche avec **Notification DPI**.
- **Appuis en direct** : quand la fenêtre est ouverte, les touches que tu tapes s'allument sur l'aperçu du clavier, et les clics, la molette, les boutons latéraux et le bouton DPI s'allument sur la souris. Avec l'effet **Réactif**, l'aperçu réagit à tes vraies frappes. RazerLite lit seulement quelles touches sont enfoncées à l'instant : rien n'est enregistré, et la lecture s'arrête quand la fenêtre est cachée.
- **Profils** (en bas à gauche) : **Nouveau** copie le profil actuel, **Supprimer** retire celui qui est affiché. Un profil « Nuit » est déjà prêt.
- **Démarrer avec Windows** : RazerLite se lance dans la barre des tâches et applique le profil. Laisse-le activé pour avoir la notification DPI en permanence.
- **Icône de la barre des tâches** : clic droit pour changer de profil ou quitter. Fermer la fenêtre la cache seulement. Une alerte apparaît quand une batterie passe sous 15 %.

Ça marche aussi en ligne de commande, depuis le dossier :

```
py -m razerlite list
py -m razerlite effect souris static --color "#ff0066"
py -m razerlite effect souris zones --colors "#ff0000" "#00ff00" "#0000ff"
py -m razerlite effect clavier breathing --color "#00ffaa" --color2 "#6600ff"
py -m razerlite dpi --stages 800,1600,3200 --active 2
py -m razerlite poll 1000
py -m razerlite apply Nuit
py -m razerlite battery
```

## 4. Macros (AutoHotkey)

Les boutons DPI et le bouton sous le pouce de la Basilisk fonctionnent sans logiciel. Pour les macros et le remappage :

1. Installe [AutoHotkey v2](https://www.autohotkey.com/).
2. Ouvre `macros\RazerLite-macros.ahk` avec le Bloc-notes. Il contient des exemples : changer de profil avec Ctrl+Alt+D ou N, la molette inclinée qui change de bureau virtuel, et une rafale ou un sprint limités à un jeu précis.
3. Double-clique sur le fichier pour l'activer.

## 5. Si ça ne marche pas

RazerLite est écrit à partir du code d'OpenRazer et d'OpenRGB, mais **il n'a pas encore été testé sur tes périphériques**. Les essais se font donc chez toi.

1. Ferme Synapse (étape 2), puis lance **diag.bat**.
2. Envoie-moi le fichier **razerlite-diag.txt** qu'il crée. Il liste ce que Windows voit et la réponse de chaque appareil, et je corrige à partir de là.

Problèmes probables :
- **« Aucun périphérique reconnu »** : Synapse tourne encore, ou ton modèle a un identifiant USB différent. Dans ce cas, le diagnostic me le donne.
- **« commande refusée »** sur le clavier sans fil : le dongle répond peut-être à un autre code. Le diagnostic me le dira aussi.
- **Le casque ne change pas** : rebranche-le, puis clique sur Appliquer.

Pour un `.exe` sans Python, lance **build-exe.bat**. Le fichier sort dans `dist\RazerLite.exe`.

## 6. Version .exe et mises à jour automatiques

**L'.exe sur ton PC, tout de suite.** Lance `build-exe.bat`. Il crée `dist\RazerLite.exe`, qui marche sans Python et que tu peux ranger où tu veux.

**Les mises à jour automatiques** passent par GitHub, gratuitement. À chaque modification envoyée sur le dépôt, GitHub fabrique tout seul un nouveau `RazerLite.exe` et le publie comme nouvelle version (fichier `.github/workflows/release.yml`). RazerLite vérifie au démarrage, puis toutes les 6 heures. Quand une version plus récente existe, un bandeau apparaît en haut de la fenêtre :

- **Mettre à jour** télécharge la nouvelle version, remplace l'ancienne et relance l'appli. Tes profils sont conservés (ils sont dans `%APPDATA%\RazerLite`).
- **Plus tard** cache le bandeau jusqu'au prochain lancement.
- Dans l'icône de la barre des tâches, **Rechercher une mise à jour** vérifie à la demande.

Mise en place (une seule fois) :

1. Crée un dépôt **public** sur GitHub, par exemple `razerlite`. Il doit être public pour que l'appli puisse lire les versions sans mot de passe.
2. Envoie-y le contenu du pack (ou donne-moi accès au dépôt et je m'en charge).
3. Dans l'onglet **Actions** du dépôt, attends la fin de « Nouvelle version » (environ 3 minutes). La version apparaît dans **Releases**.
4. Télécharge `RazerLite.exe` depuis Releases une première fois. Les suivantes arriveront toutes seules.

Si tu préfères garder la version Python (`RazerLite.bat`), écris `ton-pseudo/razerlite` dans un fichier `update-repo.txt` à côté de `RazerLite.bat` : elle se mettra à jour de la même façon, à partir de `RazerLite-pack.zip`.

Le numéro de version suit le format `0.5.N`, où N augmente à chaque build.

## Logo et polices

Le symbole à trois serpents rappelle à quoi sert le logiciel, sans reprendre le logo officiel : c'est un projet indépendant, sans lien avec Razer. Les polices Michroma et Exo 2 sont libres (licence SIL OFL, voir `razerlite/assets/OFL.txt`).
