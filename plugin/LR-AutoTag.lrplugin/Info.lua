return {
    LrSdkVersion = 12.0,
    LrSdkMinimumVersion = 12.0,

    LrToolkitIdentifier = "com.lr-autotag.plugin",
    LrPluginName = "LR-AutoTag",

    LrPluginInfoProvider = "AutoTagPluginInfoProvider.lua",

    LrLibraryMenuItems = {
        {
            title = "Ausgewählte verschlagworten",
            file = "AutoTagInteractive.lua",
        },
        {
            title = "Bibliothek verschlagworten",
            file = "AutoTagBatch.lua",
        },
    },

    VERSION = { major = 0, minor = 1, revision = 0 },
}
