# Save states macOS ARM64

Le backend natif sauvegarde et restaure la partie à une frontière VSync : RAM
PS1 et scratchpad, pile du jeu, registres ARM64, globals du jeu, allocations
enregistrées, contextes setjmp et sous-systèmes partagés avec le backend i386.
Les mappings guest et la pile/les curseurs de l'interpréteur MIPS utilisé par
les modèles 3D sont aussi conservés.
Les adresses PS1 restent des tokens de 32 bits ; les pointeurs natifs sont
relocalisés lorsque ASLR déplace l'exécutable, les allocations ou la pile.

## Utilisation

- F5 : sauvegarder dans le slot sélectionné ; F7 : charger ce slot.
- Les actions correspondantes du menu et le canal de contrôle `save`/`load`
  utilisent le même backend.
- `MEMORIES_LOAD_STATE=<chemin>` charge au démarrage ; une valeur numérique
  sélectionne un slot.
- `MEMORIES_AUTOSAVE=<secondes>` active les trois états tournants
  `auto1.state` à `auto3.state`.
- `MEMORIES_STATE_DIR` et `MEMORIES_AUTOSAVE_DIR` permettent des répertoires
  isolés. Par défaut, les fichiers vont dans `states/` du répertoire utilisateur
  de l'application. Les sauvegardes normales `.sav` restent séparées.

Le fichier est écrit dans un `.partial`, scellé par une empreinte d'intégrité,
puis renommé. Un fichier tronqué ou modifié est refusé avant la restauration.

## Compatibilité

Cette version charge les états produits par **le même exécutable ARM64**.
L'identifiant du build et l'UUID Mach-O doivent correspondre. Recompiler ou
changer de build peut rendre les états précédents incompatibles : conserver
les sauvegardes normales pour transporter une partie entre versions.

Les mods actifs et le layout/CRC du texte doivent aussi correspondre. Les
états i386 et ceux d'un émulateur PS1 ne sont pas convertis. Le format ARM64
porte une version distincte ; le format i386 existant reste inchangé.

Le compteur de frames présentées reste monotone après chargement, comme dans
upstream. Le streaming audio redémarre depuis la position du disque ; les
tests de replay ne revendiquent pas une identité des échantillons audio.

## Validation locale

Ces tests utilisent le disque USA possédé par l'utilisateur, jamais fourni
par le dépôt :

```sh
python3 tools/pc/build_arm64.py
python3 tools/pc/test_arm64_states.py --binary tmp/arm64-build/memories-arm64
python3 tools/pc/test_arm64_state_control.py --binary tmp/arm64-build/memories-arm64
```

Le premier compare une reprise dans un nouveau processus à la continuation
originale : données de duel/deck et pixels identiques, puis F5/F7 via SDL dummy.
Le second vérifie trois rechargements, la RAM du jeu, le refus sans mutation de
fichiers corrompus/tronqués/i386, les incompatibilités de mods/langue/exécutable
et la rotation/restauration des autosaves.
Le canal loopback peut nécessiter l'autorisation réseau du sandbox.

Les tests sans disque de `test_native.py` couvrent le conteneur, son intégrité,
les identités de régions, la recréation des allocations, les pointeurs de fin
de tableau, ASLR et le refus avant mutation. Ils passent aussi sous ASan/UBSan ;
les changements de pile en assembleur sont vérifiés séparément sans les
annotations de pile des sanitizers.

L'affichage et l'écoute en fenêtre réelle restent à valider manuellement.

Reprises supplémentaires validées : fusion et équipement à frame 9000,
combat 3D à frame 20000 avec retour au terrain et dégâts conservés :

```sh
python3 tools/pc/test_arm64_gameplay.py --case fusion --state-frame 9000
python3 tools/pc/test_arm64_gameplay.py --case equip --state-frame 9000
python3 tools/pc/test_arm64_gameplay.py --case animated-battle --state-frame 20000
```
