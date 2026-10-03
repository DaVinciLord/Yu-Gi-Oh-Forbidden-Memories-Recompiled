# Investigation macOS arm64 — 2026-10-02

## Périmètre et état Git

Nouveau dépôt : `496dd953620302cdcf234f176cde53afdf103614`, cloné dans
`/Users/vincentmetton/Code/FM/new-port`. Checkout initial propre sur master;
branche locale créée : `spike/macos-arm64`. Aucun changement de code, commit,
push ou fichier propriétaire. Ce rapport est le seul ajout suivi proposé.

Ancien dépôt : checkout main `90cc0a9f894386856986b0cafb058c8588674d95`,
lecture seule dans `/Users/vincentmetton/Code/FM/old-reference`.
Workflow également lu à `v0.6.2` (`eae4221bddef3b61142fed08b9381b78789791fe`).
Son runtime PSXRecomp épinglé est `ab5e805191323a020e06f6d0c7d40dffbd3e1167`;
le checkout main épingle `1965b2df424da03483a5370340433a862f78f103`.
Le sous-module a été initialisé pour lecture; le pin de v0.6.2 a été lu avec
git show sans changer le checkout. Ne pas confondre ces deux versions.

Pas d'AGENTS.md trouvé dans les clones. Consignes lues :
`.github/copilot-instructions.md`, README, documentation PC/build/release,
plan du port et règles de validation. Le README annonce un jeu jouable;
plusieurs introductions des notes décrivent encore l'ancien bring-up.
Les sources actuelles font foi. Les sondes et logs restent dans le répertoire
ignoré `tmp/macos-investigation/` du nouveau dépôt.

Machine : macOS 26.6.2, arm64, Apple Clang 21.0.0, Xcode présent.
CMake/Ninja absents du PATH; GNU objcopy/readelf absents.

## État actuel vérifié

- `G32` fonctionne avec Apple Clang, `MEMORIES_PC` et `-fms-extensions` :
  pointeur hôte 8 octets, pointeur stocké 4 octets, structure sonde 8 octets.
  `PSXLONG` devient int sur LP64. `CALL32` ne fait qu'un cast : aucun resolver.
- Inclusion de `ygo_types.h` : assertions existantes acceptées, avec avertissements
  de casts et de constantes étendues. Cela ne prouve pas tous les layouts du jeu.
- Test existant `core_test.c` compilé et exécuté nativement : RNG du jeu,
  comparateur, résolution des alias, limites et scratchpad passent.
  Il teste `MemoriesMemory`, pas le mapping réel du runtime.
- Les dix scénarios existants de `game_files_test.c` passent avec disque
  synthétique et `-D_DARWIN_C_SOURCE`. Sans ce define, la compilation stricte
  échoue sur mkdtemp dans `tests/pc/scratch.h`.
- `file` confirme Mach-O 64-bit executable arm64 pour les sondes.
- Census syntaxique des 514 unités résidentes avec G32 activé : 233 passent,
  281 échouent. Les diagnostics recueillis sont des attributs de section ELF
  invalides pour Mach-O (1493 occurrences, avec limite de diagnostics dans
  16 unités). Pas de compilation objet complète, linkage ou test gameplay.

## Reproduction du chemin existant

1. `./play.sh` : arrêt sur `objcopy readelf` manquants, conseils exclusivement Linux.
2. `./build-pc.sh` dans le sandbox : aucun miroir Debian accessible. Limitation
   réseau de l'environnement, pas un diagnostic de compatibilité du port.
3. Même commande avec réseau autorisé : téléchargement de 168 paquets Debian
   i386, puis CMake Linux x86_64 et Ninja Linux. Arrêt réel :
   `OSError: [Errno 8] Exec format error: 'cmake'`.
4. Compilation directe de `image.c`, sans enlever ses protections : assertion
   `sizeof(void *) == 4`, MAP_FIXED_NOREPLACE absent, ucontext Darwin incompatible
   avec gregs/REG_EAX/REG_EIP et exigence _XOPEN_SOURCE.
5. Sonde `-m32` : linkage impossible (`unsupported architecture ... armv4t`).
   Il ne produit pas un exécutable macOS arm64.

Logs : `play.log`, `build.log`, `build-network.log`, `image.log`, `ptr32.log`,
`layout.log`, `empty.log`, `game-syntax.json` sous tmp/macos-investigation.
CMake complet et suite CTest complète non exécutés; aucun jeu lancé.

## Blockers et modification minimale recommandée

| Problème / pourquoi | Nature | Ancien projet | Action minimale proposée |
|---|---|---|---|
| Darwin traité comme Linux par build_game32/fetch_tools; dépendances Debian, outils GNU, -m32, options x86 | OS + architecture | Détection Darwin et dépendances CMake natives | Ajouter une cible macos-arm64 explicite, outils natifs et dépendances SDL3/FreeType/PNG; garder les deux chemins actuels |
| Sections .data/.sdata, symboles absolus, renommages objcopy et script GNU ld | Mach-O | psx_bss.h montre segment,section sur Apple | Abstraction ciblée des attributs et backend Mach-O pour les pins/sections; aucune modification du layout console |
| image.c impose ILP32; guest pointers = host pointers | 32→64 | PSXRecomp traduit des adresses via un autre runtime | Prouver d'abord si le modèle d'adresses fixes reste viable sur Darwin; ne pas supprimer l'assertion avant preuve |
| memfd_create et MAP_FIXED_NOREPLACE; alias RAM partagés et scratchpad bas | Linux + VM macOS | Pas de solution directement interchangeable | Backend Darwin de réservation sans écrasement et mémoire partagée; vérifier les alias et la granularité des pages |
| Pointeurs stockés G32 tronquent un pointeur natif situé au-delà de 4 Gio | 32→64 | Ancien runtime sépare adresse invitée et pointeur hôte | Arena contrôlée pour données invitées; resolver/identifiants pour fonctions; audit des callbacks, allocations et casts |
| branch_thunks.c, stubs générés, MIPS bridge, setjmp_i386.S | i386 / ABI | Dispatch PSXRecomp conceptuellement utile | Résolution explicite des appels invités et bridges AArch64 respectant arguments/retours; garder la table de fonctions actuelle |
| Réparation des accès nuls via décodage ModRM et registres x86 | i386 + OS | Non transférable | Inventorier les sites, remplacer les accès console bas par helpers ciblés plutôt que copier le décodeur x86 |
| VSync/state_i386.S, piles et registres 32-bit, sauvegardes de stack native | i386 / ABI | psx_fiber.c illustre ucontext Darwin, pas le format des états | Backend de contexte arm64; cartes mémoire normales conservées, save states natifs explicitement incompatibles jusqu'à implémentation |
| platform_common/debug/crash utilisent ucontext Linux; monitor utilise /proc, ptrace, memfd | OS + architecture | Diagnostics/fibres comme références | Petits backends Darwin pour timers/contexte; fonctions diagnostics non disponibles annoncées explicitement |
| Chemins d'exécutable/restart via /proc/self/exe; données utilisateur XDG | OS | SDL_GetBasePath présent dans ancien runtime | Résolution Darwin du binaire et Application Support, préserver override/portable mode et tests Unicode |
| Rendu GL mélange immediate mode, GLSL 120/130 et picture pass exigeant GL ≥3.0 | macOS graphique | Ancien Vulkan/MoltenVK sans rapport direct | Premier affichage via software GPU + SDL_Renderer existants; ensuite présentation/shaders compatibles core, sans migration Vulkan |
| Audio SPU + stream SDL3, input SDL3; evdev déjà gardé par __linux__ | Pas de blocker prouvé | APIs SDL conceptuellement similaires | Conserver, tester périphériques/audio/timing après runtime; ne pas porter ALSA/evdev |
| Mods objet ELF32 EM_386 et hooks jmp x86, exports/adresses 32-bit | Architecture | Ancien overlay loader conceptuel seulement | Déclarer les mods binaires i386 incompatibles; backend arm64 séparé requis avant parité, conserver mods de données |
| CMake tests imposent -m32 et options ELF sous NOT WIN32/NOT MSVC | Build/OS/architecture | CMake natif en référence | Séparer tests portables des tests ABI32, ajouter tests de layouts arm64, ne pas simplement ignorer les échecs |
| package.py et CI ne connaissent que Linux/Windows | Livraison | Matrice macos-15, packaging partagé | Ajouter CI core arm64 d'abord; archive/app et dépendances/signature ensuite |

## Point critique : mémoire basse

Le Mach-O standard de la sonde réserve `__PAGEZERO` de 0 à 4 Gio, et le code
est chargé au-dessus de 4 Gio. Les mmap utilisés comme simples hints pour
0x10000, 0x1f800000, 0x80000000 et 0xa0000000 reviennent tous au-dessus de
4 Gio. Ce test ne force ni n'écrase une réservation.
Une sonde distincte liée avec `-pagezero_size 0x4000` compile mais termine
avec signal 9, sans diagnostic : raison non déterminée. Ne pas considérer
ce flag comme un correctif validé. Aucun réglage système/signature ou autre
contournement n'a été appliqué. La viabilité des adresses fixes est la première
question à résoudre, avant le linkage du jeu.

## Old vs New

v0.6.2 sélectionne macos-15 pour arm64, macos-15-intel pour x64 et un deployment
target 11.0; installe SDL3 et les outils Vulkan/shaderc/MoltenVK. CMake délègue
le runtime à PSXRecomp. Le workflow produit un setup host puis un zip qui
permet la génération/recompilation locale : ce n'est pas la chaîne du nouveau
jeu déjà décompilé.

Réutilisable directement avec adaptation limitée : conventions CI Darwin,
détection des outils/dépendances, idée de macros Mach-O de sections.
Référence conceptuelle : audio/input SDL, chemins, fibres, contrôle des dylibs,
rpath, signature et structure d'app du packager macOS partagé. Le workflow
v0.6.2 appelle package_setup_host.sh, pas ce packager .app générique.
À implémenter dans le nouveau port : linkage des globals, mémoire, appels
invités, bridges MIPS, contexte, états et mods arm64. Aucun remplacement du
runtime par PSXRecomp proposé. MoltenVK n'est pas requis par le nouveau code.

La présentation actuelle utilise glBegin/GL_QUADS/glOrtho. Passer seulement
le contexte à core 3.2 ne suffit pas : Apple documente la suppression de ces
fonctions et l'adaptation des shaders. Sources :
https://developer.apple.com/library/archive/documentation/GraphicsImaging/Conceptual/OpenGL-MacProgGuide/UpdatinganApplicationtoSupportOpenGL3/UpdatinganApplicationtoSupportOpenGL3.html
https://wiki.libsdl.org/SDL3/SDL_GL_SetAttribute
Documentation SDL obtenue avec Context7 (library puis docs).

## Plan minimal, commits séparés

1. **Preuve mémoire/ABI sans ROM** : réservations Darwin, alias partagés,
   scratchpad, layouts/offsets G32, stockage et résolution d'un callback natif.
   Tester la faisabilité sous Mach-O normal et dans un binaire arm64 valide.
   Si préserver les adresses échoue, présenter une alternative ciblée avant
   toute généralisation de translation des pointeurs.
2. **Build portable et core CI** : cible arm64 explicite, attributs Mach-O,
   dépendances natives, tests portables et tests ABI32 distingués.
3. **Runtime headless** : pins des globals, resolver/bridges arm64,
   accès bas, timers, contexte et lancement jusqu'à lecture du PS-X EXE.
   Fonctionnalités non disponibles explicites, pas de stubs de succès silencieux.
4. **Première fenêtre** : réutiliser software GPU + présentation SDL existante,
   picker/paths; vérifier title/menu avec la ROM. Audio et input ensuite.
5. **Parité et livraison** : renderer GL core, états arm64, mods arm64,
   packaging .app/zip, signature et release CI.

Pour chaque lot : garder Linux/Windows, réutiliser tests existants, ajouter
seulement les tests de contrats modifiés. Tests de matching console/overlays
à exécuter si les sources partagées changent, avec les inputs retail nécessaires.
Les checks de layouts seuls ne remplacent ni matching ni smoke gameplay.

## Premier milestone

Un **test arm64 sans ROM** qui réserve la RAM PS1 sans conflit, vérifie que
KSEG0/KSEG1/miroir physique partagent réellement les octets, accède au scratchpad,
préserve les offsets des structures et appelle correctement un callback stocké
sur 32 bits. C'est une étape plus petite et plus utile que promettre déjà le jeu.
Ensuite : binaire du jeu arm64 headless jusqu'au chargement de l'exécutable.

## Inputs et risques

Placer le .bin légal du disque **USA SLUS-01411** dans
`/Users/vincentmetton/Code/FM/new-port/game/` (nom quelconque terminé en .bin).
Le lecteur extrait SLUS_014.11; ne pas fournir une image PAL/Japon.
Le matching console attend en plus `game/SLUS_014.11` et les inputs listés
par `config/slus_01411/files.sha256`. Aucun input nécessaire pour les sondes
réalisées et le premier milestone proposé.

Risques majeurs : troncature des callbacks/allocations natives, structures
host de src/pc exemptes du checker G32, adresses absolues et alias,
liens GPU 24-bit, piles/contextes et états sérialisés, ABI du bridge MIPS,
cohérence des hooks/code exécutable sur arm64. Les assertions de layout
existantes ne constituent pas une preuve de comportement 64-bit.

Investigation arrêtée ici. Aucun correctif de production ni réécriture engagé.
