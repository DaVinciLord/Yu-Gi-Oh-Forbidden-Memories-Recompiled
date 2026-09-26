/* The updater's thread and its notices (update_runtime.h). The thread owns
 * `job` from Update_* starting it until it publishes `done`; the main
 * thread reads the result only after that, so nothing else is shared. */
#define _GNU_SOURCE
#include "pc/compat/fs.h"
#include "update_runtime.h"
#include "update.h"
#include "update_net.h"
#include "menu.h"
#include "paths.h"
#include "platform.h"
#include "settings.h"
#include "pc/compat/signal.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The release this executable is (tools/pc/build_game32.py writes it from
 * the tag it was built for), or "" for a development build. */
extern const char Memories_Version[];

#define REPOSITORY "Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"
#define RELEASES_API "https://api.github.com/repos/" REPOSITORY "/releases?per_page=30"
#define RELEASES_PAGE "https://github.com/" REPOSITORY "/releases"
#define CHECK_SECONDS 20
#define DOWNLOAD_SECONDS 1800
#define LIST_LIMIT (8L * 1024 * 1024)
#ifdef _WIN32
#define EXECUTABLE "memories-pc.exe"
#define ASSET_SUFFIX "-windows.zip"
#else
#define EXECUTABLE "memories-pc"
#define ASSET_SUFFIX "-linux.tar.gz"
#endif

enum { JOB_CHECK = 1, JOB_INSTALL };
enum { FOUND_NEWER = 1, FOUND_LATEST, CHECK_FAILED, INSTALLED, INSTALL_FAILED };

static struct {
    int running;      /* main thread: a job has started and not been answered */
    int kind, manual; /* what the job is, and whether the player asked for it */
    int done;         /* the thread's answer (atomic); 0 while it works */
    long received;    /* bytes of the download so far (atomic) */
    UpdateRelease release;
    char why[256];
} job;

static UpdateRelease offered; /* the release the notice shown is about */
static int progress_shown;

static const char *current_version(void)
{
    const char *named = getenv("MEMORIES_UPDATE_CURRENT");
    return named && *named ? named : Memories_Version;
}

static int known_version(void) { return Update_ParseVersion(current_version(), NULL); }

const char *Update_VersionLabel(void)
{
    static char label[96];
    if (known_version()) snprintf(label, sizeof(label), "Version %s", current_version());
    else snprintf(label, sizeof(label), "Development build");
    return label;
}

static int flag(const char *name)
{
    const char *value = getenv(name);
    return value && *value && strcmp(value, "0");
}

/* updates/<name> in the user directory, without creating anything. */
static void user_path(char *out, size_t size, const char *name)
{
    snprintf(out, size, "%s/updates/%s", Paths_UserDir(), name);
}

static void read_skip(char *out, size_t size)
{
    char path[1024];
    FILE *file;
    out[0] = '\0';
    user_path(path, sizeof(path), "skip.txt");
    if ((file = fopen(path, "r"))) {
        if (!fgets(out, (int)size, file)) out[0] = '\0';
        out[strcspn(out, "\r\n")] = '\0';
        fclose(file);
    }
}

static void write_skip(const char *tag)
{
    char path[1024];
    FILE *file;
    if (Paths_User(path, sizeof(path), "updates/skip.txt")) return;
    if ((file = fopen(path, "w"))) {
        fprintf(file, "%s\n", tag);
        fclose(file);
    }
}

/* --- the thread ------------------------------------------------------ */

typedef struct { char *data; long size, capacity; } Buffer;

static int to_buffer(const void *data, size_t size, void *context)
{
    Buffer *buffer = context;
    if (buffer->size + (long)size + 1 > buffer->capacity) {
        long capacity = buffer->capacity ? buffer->capacity : 65536;
        char *grown;
        while (capacity < buffer->size + (long)size + 1) capacity *= 2;
        if (capacity > LIST_LIMIT || !(grown = realloc(buffer->data, (size_t)capacity))) return 1;
        buffer->data = grown;
        buffer->capacity = capacity;
    }
    memcpy(buffer->data + buffer->size, data, size);
    buffer->size += (long)size;
    buffer->data[buffer->size] = '\0';
    return 0;
}

static int check(void)
{
    const char *url = getenv("MEMORIES_UPDATE_URL");
    Buffer list = {0};
    UpdateVersion current;
    char skip[64] = "";
    int prereleases = Settings_Get(SET_UPDATE_PRERELEASES), found;
    if (!url || !*url) url = RELEASES_API;
    if (!job.manual) read_skip(skip, sizeof(skip));
    /* Someone running a preview wants to hear of the next one. */
    if (Update_ParseVersion(current_version(), &current) && current.pre[0]) prereleases = 1;
    if (UpdateNet_Get(url, CHECK_SECONDS, to_buffer, &list, job.why, sizeof(job.why)) || !list.data) {
        free(list.data);
        return CHECK_FAILED;
    }
    found = Update_PickRelease(list.data, current_version(), prereleases, skip, ASSET_SUFFIX, &job.release);
    free(list.data);
    if (found < 0) {
        snprintf(job.why, sizeof(job.why), "GitHub's list of releases could not be read.");
        return CHECK_FAILED;
    }
    return found ? FOUND_NEWER : FOUND_LATEST;
}

typedef struct { FILE *file; long limit; } Download;

static int to_file(const void *data, size_t size, void *context)
{
    Download *download = context;
    long received = __atomic_load_n(&job.received, __ATOMIC_RELAXED) + (long)size;
    if (received > download->limit || fwrite(data, 1, size, download->file) != size) return 1;
    __atomic_store_n(&job.received, received, __ATOMIC_RELAXED);
    return 0;
}

static int install(void)
{
    const UpdateRelease *release = &job.release;
    char folder[1024], archive[1024], stage[1024], root[1024], cleanup[1024], hex[65];
    Download download = {NULL, release->asset_size ? release->asset_size : 1024L * 1024 * 1024};
    int failed;
    if (!Paths_Contained(release->asset_name) || strchr(release->asset_name, '/') ||
        Paths_User(folder, sizeof(folder), "updates/stage") || /* makes updates/ */
        (size_t)snprintf(archive, sizeof(archive), "%s/updates/%s", Paths_UserDir(), release->asset_name) >= sizeof(archive)) {
        snprintf(job.why, sizeof(job.why), "The release's file name is not usable here.");
        return INSTALL_FAILED;
    }
    snprintf(stage, sizeof(stage), "%s/updates/stage", Paths_UserDir());
    user_path(cleanup, sizeof(cleanup), "cleanup.txt");
    Update_RemoveTree(stage);
    if (!(download.file = fopen(archive, "wb"))) {
        snprintf(job.why, sizeof(job.why), "Could not write the download to %s.", archive);
        return INSTALL_FAILED;
    }
    failed = UpdateNet_Get(release->asset_url, DOWNLOAD_SECONDS, to_file, &download, job.why, sizeof(job.why));
    if (fclose(download.file)) failed = 1;
    if (!failed && release->asset_size && __atomic_load_n(&job.received, __ATOMIC_RELAXED) != release->asset_size) {
        snprintf(job.why, sizeof(job.why), "The download is incomplete.");
        failed = 1;
    }
    if (!failed && !strncmp(release->digest, "sha256:", 7) &&
        (Update_Sha256File(archive, hex) || strcmp(hex, release->digest + 7))) {
        snprintf(job.why, sizeof(job.why), "The download does not match the release's SHA-256.");
        failed = 1;
    }
    if (!failed) failed = Update_Extract(archive, stage, job.why, sizeof(job.why));
    if (!failed && Update_StagedRoot(stage, root, sizeof(root))) {
        snprintf(job.why, sizeof(job.why), "The archive is not laid out as a release.");
        failed = 1;
    }
    if (!failed && !Update_IsPackagedInstall(root, EXECUTABLE)) {
        snprintf(job.why, sizeof(job.why), "The archive is not this game's release for this system.");
        failed = 1;
    }
    if (!failed) failed = Update_Install(root, Paths_ProgramDir(), cleanup, job.why, sizeof(job.why));
    remove(archive);
    Update_RemoveTree(stage);
    return failed ? INSTALL_FAILED : INSTALLED;
}

static void *run(void *unused)
{
    int answer;
    (void)unused;
    answer = job.kind == JOB_CHECK ? check() : install();
    __atomic_store_n(&job.done, answer, __ATOMIC_RELEASE);
    return NULL;
}

static int start(int kind, int manual)
{
    pthread_t thread;
    sigset_t all, previous;
    int error;
    if (job.running) return -1;
    job.kind = kind;
    job.manual = manual;
    job.done = 0;
    job.received = 0;
    job.why[0] = '\0';
    if (kind == JOB_INSTALL) job.release = offered;
    /* The game's clock signal belongs to the main thread (platform_common.c). */
    sigfillset(&all);
    pthread_sigmask(SIG_BLOCK, &all, &previous);
    error = pthread_create(&thread, NULL, run, NULL);
    pthread_sigmask(SIG_SETMASK, &previous, NULL);
    if (error) return -1;
    pthread_detach(thread);
    job.running = 1;
    return 0;
}

/* --- the notices ----------------------------------------------------- */

/* Why this copy cannot put a release over itself, or NULL if it can. */
static const char *cannot_install(const UpdateRelease *release)
{
    if (!release->asset_url[0]) return "the release has no download for this system";
    if (!Update_IsPackagedInstall(Paths_ProgramDir(), EXECUTABLE)) return "it is not an unpacked release folder";
    if (UpdateNet_Virtualized() || !Update_CanWrite(Paths_ProgramDir())) return "its folder cannot be written to";
    return NULL;
}

static int can_install(const UpdateRelease *release) { return !cannot_install(release); }

static void open_url(const char *url)
{
    if (Platform_OpenUrl(url && *url ? url : RELEASES_PAGE))
        fprintf(stderr, "memories-pc: update: could not open %s\n", url && *url ? url : RELEASES_PAGE);
}

static void show_progress(void);

static void begin_install(void)
{
    if (start(JOB_INSTALL, 1)) return;
    fprintf(stderr, "memories-pc: update: downloading %s\n", offered.asset_url);
    show_progress();
}

static void chosen_newer(int button, int *quit)
{
    (void)quit;
    if (!can_install(&offered)) button++; /* no Update now button */
    switch (button) {
    case 0: begin_install(); break;
    case 1: open_url(offered.page); break;
    case 2: write_skip(offered.tag); break;
    default: break;
    }
}

static void show_newer(void)
{
    static const char *const with_install[] = {"Update now", "Release page", "Skip this version", "Later"};
    char title[128], text[1024];
    const char *why_not = cannot_install(&offered);
    int installable = !why_not;
    snprintf(title, sizeof(title), "%s %s is out", offered.prerelease ? "Pre-release" : "Version", offered.tag);
    if (installable)
        snprintf(text, sizeof(text),
                 "%s is available; you have %s.\n\n"
                 "Update now downloads it (%.1f MB) and installs it over this copy. Your saves, settings, "
                 "mods and disc image stay as they are. The new version starts the next time you open the game.",
                 offered.title, current_version(), offered.asset_size / 1e6);
    else
        snprintf(text, sizeof(text),
                 "%s is available; you have %s.\n\n"
                 "This copy cannot update itself (%s), so download the new version from its release page.",
                 offered.title, current_version(), why_not);
    Menu_ShowNotice(title, text, installable ? with_install : with_install + 1, installable ? 4 : 3, -1, chosen_newer);
}

static void chosen_progress(int button, int *quit)
{
    (void)button;
    (void)quit;
    progress_shown = 0; /* Hide: the result still shows when it is done */
}

static void progress_text(char *text, size_t size)
{
    long received = __atomic_load_n(&job.received, __ATOMIC_RELAXED);
    if (job.release.asset_size)
        snprintf(text, size, "Downloading %s: %.1f of %.1f MB.", job.release.asset_name, received / 1e6,
                 job.release.asset_size / 1e6);
    else
        snprintf(text, size, "Downloading %s: %.1f MB.", job.release.asset_name, received / 1e6);
}

static void show_progress(void)
{
    static const char *const hide[] = {"Hide"};
    char title[128], text[512];
    snprintf(title, sizeof(title), "Updating to %s", offered.tag);
    progress_text(text, sizeof(text));
    Menu_ShowNotice(title, text, hide, 1, 0, chosen_progress);
    progress_shown = 1;
}

static void chosen_installed(int button, int *quit)
{
    if (button == 0) *quit = 1;
}

static void chosen_failed(int button, int *quit)
{
    (void)quit;
    if (button == 0) open_url(offered.page);
}

static void chosen_plain(int button, int *quit)
{
    (void)button;
    (void)quit;
}

static void chosen_releases(int button, int *quit)
{
    (void)quit;
    if (button == 0) open_url(RELEASES_PAGE);
}

void Update_Frame(void)
{
    int done;
    char text[1024];
    if (!job.running) return;
    done = __atomic_load_n(&job.done, __ATOMIC_ACQUIRE);
    if (!done) {
        static unsigned frames;
        if (job.kind == JOB_INSTALL && progress_shown && Menu_NoticeShown() && ++frames % 15 == 0) {
            progress_text(text, sizeof(text));
            Menu_SetNoticeText(text);
        }
        return;
    }
    job.running = 0;
    if (job.kind == JOB_INSTALL) progress_shown = 0;
    switch (done) {
    case FOUND_NEWER:
        offered = job.release;
        fprintf(stderr, "memories-pc: update: %s is out (running %s)\n", offered.tag, current_version());
        if (!job.manual && Settings_Get(SET_UPDATE_AUTO) && can_install(&offered)) {
            start(JOB_INSTALL, 0); /* quietly; the result is announced */
            fprintf(stderr, "memories-pc: update: installing %s automatically\n", offered.tag);
        } else {
            show_newer();
        }
        break;
    case FOUND_LATEST:
        fprintf(stderr, "memories-pc: update: no newer release to offer than %s\n", current_version());
        if (job.manual) {
            static const char *const ok[] = {"OK"};
            snprintf(text, sizeof(text), "%s is the newest release.", current_version());
            Menu_ShowNotice("You're up to date", text, ok, 1, 0, chosen_plain);
        }
        break;
    case CHECK_FAILED:
        fprintf(stderr, "memories-pc: update: check failed: %s\n", job.why);
        if (job.manual) {
            static const char *const buttons[] = {"Releases page", "Close"};
            snprintf(text, sizeof(text), "%s\n\nYou can look at the releases page instead.", job.why);
            Menu_ShowNotice("Could not check for updates", text, buttons, 2, 1, chosen_releases);
        }
        break;
    case INSTALLED: {
        static const char *const buttons[] = {"Quit now", "Later"};
        fprintf(stderr, "memories-pc: update: installed %s into %s\n", job.release.tag, Paths_ProgramDir());
        snprintf(text, sizeof(text),
                 "%s is installed. This session keeps running %s; start the game again to play the new version.",
                 job.release.tag, current_version());
        Menu_ShowNotice("Update installed", text, buttons, 2, 1, chosen_installed);
        break;
    }
    case INSTALL_FAILED: {
        static const char *const buttons[] = {"Release page", "Close"};
        fprintf(stderr, "memories-pc: update: install failed: %s\n", job.why);
        snprintf(text, sizeof(text), "%s\n\nThis copy was not changed. You can download %s from its release page.",
                 job.why, job.release.tag);
        Menu_ShowNotice("The update could not be installed", text, buttons, 2, 1, chosen_failed);
        break;
    }
    default: break;
    }
}

void Update_CheckNow(void)
{
    if (job.running) return;
    if (!known_version()) {
        static const char *const buttons[] = {"Releases page", "Close"};
        Menu_ShowNotice("Development build",
                        "This build was not made from a release, so it has no version to compare with the "
                        "releases. The releases page lists what is out.",
                        buttons, 2, 1, chosen_releases);
        return;
    }
    start(JOB_CHECK, 1);
}

void Update_OpenReleases(void) { open_url(RELEASES_PAGE); }

void Update_Start(void)
{
    char cleanup[1024];
    const char *url = getenv("MEMORIES_UPDATE_URL");
    int tested = url && *url;
    user_path(cleanup, sizeof(cleanup), "cleanup.txt");
    Update_Cleanup(cleanup); /* what an update could not remove while it ran */
    if (flag("MEMORIES_NO_UPDATE_CHECK") || getenv("MEMORIES_HEADLESS") || !Settings_Get(SET_UPDATE_CHECK) ||
        !known_version())
        return;
    /* Scripted runs are tests: they reach the network only when told where. */
    if (!tested && (getenv("MEMORIES_SDL_SCRIPT") || getenv("MEMORIES_INPUT"))) return;
    start(JOB_CHECK, 0);
}
