# Build macOS ARM64

La branche d'intégration fournit un build natif Apple Silicon avec Python 3,
les outils de développement Xcode et le SDK macOS. Aucune installation
Homebrew, CMake/Ninja globale ni commande pip n'est nécessaire.

```sh
python3 tools/pc/build_arm64.py
tmp/arm64-build/memories-arm64
```

Le premier build télécharge les archives officielles et vérifie leurs SHA-256.
LLVM/Clang 21.1.8 est installé dans `tmp/pc/llvm-macos`, CMake 4.4.3 et Ninja
1.13.2 dans `tmp/pc/tools/macos`. SDL3 3.4.16, FreeType 2.14.3, libpng 1.6.58,
zlib 1.3.2 et zstd 1.5.7 sont compilés statiquement dans `tmp/pc/macos-deps`.
Le SDK Xcode est découvert avec `xcrun --sdk macosx --show-sdk-path`.
Les builds suivants réutilisent les dépendances lorsque leur configuration et
leurs empreintes n'ont pas changé.

Le disque USA possédé par le joueur est nécessaire pour lancer le jeu, pas
pour construire le binaire. Les polices sont découvertes par CoreText parmi
les polices système ; FreeType les dessine.

Contrôles sans disque :

```sh
python3 tools/pc/test_llvm_guest.py
python3 tools/pc/test_macos_linkage.py --binary tmp/arm64-build/memories-arm64
```

Le contrôle de linkage lit les véritables dépendances Mach-O, refuse les
bibliothèques tierces extérieures au dépôt, vérifie l'architecture ARM64 des
archives et dessine des glyphes Latin/japonais avec les polices découvertes.
Le compilateur LLVM utilise aussi le zstd local, même si son llvm-config
contient le chemin absolu de la machine de build officielle.

L'intégration de ce driver à la commande de build commune, à `play.sh` et à
la CI reste en cours. Le packaging `.app` est différé. Pour les états natifs,
voir [macos-arm64-save-states.md](macos-arm64-save-states.md).
