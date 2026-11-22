using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

internal static class TocaRecomp
{
    private const string Version = "0.1.0-preview.3";
    private const string SupportPrefix = "support/";

    private const string Usage =
        "Usage: TocaRecomp.exe --disc PATH [--data-dir PATH] [--setup-dir PATH]\n" +
        "                     [--windowed | --fullscreen] [--direct | --setup-only] [--road-america PATH]\n" +
        "                     [--dtm-mod PATH] [--no-save] [--frame-limit COUNT]\n\n" +
        "Run TOCA Race Driver 3 for Windows 11 x64 using your PS2 disc (SLUS-21182 v1.02).\n" +
        "--disc PATH          ISO, DVD CHD, or folder containing the extracted disc files.\n" +
        "--data-dir PATH      Saves, settings, caches, and runtime logs. Defaults to the launcher folder.\n" +
        "--setup-dir PATH     Portable toolchain and build files. Defaults to setup under the data folder.\n" +
        "--road-america PATH  Enable the locally built Road America add-on and use its own memory card.\n" +
        "--dtm-mod PATH       Load local DTM car overlays and use a separate memory card.\n" +
        "--windowed          Open a window (default).\n" +
        "--fullscreen        Open fullscreen.\n" +
        "--direct            Launch an existing build without running setup.\n" +
        "--setup-only        Prepare or validate the local build and exit.\n" +
        "--no-save           Run without a memory card.\n" +
        "--frame-limit COUNT Stop after this many guest frames (0 means no limit).\n" +
        "--help              Show this help message.\n" +
        "--version           Show the launcher version.";

    private static int Main(string[] args)
    {
        if (args.Length == 0 || Array.IndexOf(args, "--help") >= 0)
        {
            Console.WriteLine(Usage);
            return 0;
        }
        if (args.Length == 1 && args[0] == "--version")
        {
            Console.WriteLine("TOCA Race Driver 3 Recompilation " + Version);
            return 0;
        }

        try
        {
            return Launch(args);
        }
        catch (ArgumentException error)
        {
            Console.Error.WriteLine(error.Message);
            return 2;
        }
        catch (Win32Exception error)
        {
            Console.Error.WriteLine("Could not start the Windows launcher helper. " + error.Message);
            return 3;
        }
        catch (IOException error)
        {
            Console.Error.WriteLine("Could not access the launcher files. " + error.Message);
            return 3;
        }
        catch (UnauthorizedAccessException error)
        {
            Console.Error.WriteLine("Could not access the launcher files. " + error.Message);
            return 3;
        }
    }

    private static int Launch(string[] args)
    {
        string disc = null;
        string data = AppDomain.CurrentDomain.BaseDirectory;
        string setup = null;
        string roadAmerica = null;
        string dtmMod = null;
        string display = null;
        bool direct = false;
        bool setupOnly = false;
        bool noSave = false;
        uint frameLimit = 0;

        for (int index = 0; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--disc": disc = ReadPath(args, ref index); break;
                case "--data-dir": data = ReadPath(args, ref index); break;
                case "--setup-dir": setup = ReadPath(args, ref index); break;
                case "--road-america": roadAmerica = ReadPath(args, ref index); break;
                case "--dtm-mod": dtmMod = ReadPath(args, ref index); break;
                case "--windowed":
                case "--fullscreen":
                    if (display != null && display != args[index])
                        throw new ArgumentException("Choose either --windowed or --fullscreen.");
                    display = args[index];
                    break;
                case "--direct": direct = true; break;
                case "--setup-only": setupOnly = true; break;
                case "--no-save": noSave = true; break;
                case "--frame-limit":
                    if (++index == args.Length || !uint.TryParse(args[index], NumberStyles.None,
                        CultureInfo.InvariantCulture, out frameLimit))
                        throw new ArgumentException("--frame-limit requires a nonnegative integer.");
                    break;
                default: throw new ArgumentException("Unknown option " + args[index] + ". Run --help for usage.");
            }
        }

        if (disc == null) throw new ArgumentException("Provide your disc path with --disc.");
        if (direct && setupOnly) throw new ArgumentException("Choose either --direct or --setup-only.");
        if (setup == null) setup = Path.Combine(data, "setup");
        if (!File.Exists(disc) && !Directory.Exists(disc))
            throw new ArgumentException("Disc source does not exist: " + disc);
        if (direct && !Directory.Exists(setup))
            throw new IOException("This build is not prepared. Run once without --direct to set up the game.");
        if (roadAmerica != null && !Directory.Exists(roadAmerica))
            throw new ArgumentException("Road America add-on directory does not exist: " + roadAmerica);
        if (dtmMod != null && !Directory.Exists(dtmMod))
            throw new ArgumentException("DTM mod directory does not exist: " + dtmMod);

        string support = PrepareSupport(data);
        var command = new List<string> {
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", support,
            "-Disc", disc, "-DataDirectory", data, "-SetupDirectory", setup
        };
        if (direct) command.Add("-Direct");
        if (setupOnly) command.Add("-SetupOnly");
        if (noSave) command.Add("-NoSave");
        if (roadAmerica != null)
        {
            command.Add("-RoadAmericaDirectory");
            command.Add(roadAmerica);
        }
        if (dtmMod != null)
        {
            command.Add("-DtmModDirectory");
            command.Add(dtmMod);
        }
        if (display == "--fullscreen") command.Add("-Fullscreen");
        if (frameLimit != 0)
        {
            command.Add("-FrameLimit");
            command.Add(frameLimit.ToString(CultureInfo.InvariantCulture));
        }

        string powershellHome = Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0");
        string powershell = Path.Combine(powershellHome, "powershell.exe");
        var startInfo = new ProcessStartInfo(powershell, string.Join(" ", command.ConvertAll(Quote))) { UseShellExecute = false };
        startInfo.EnvironmentVariables["PSModulePath"] = Path.Combine(powershellHome, "Modules");
        using (Process helper = Process.Start(startInfo))
        {
            helper.WaitForExit();
            return helper.ExitCode;
        }
    }

    private static string PrepareSupport(string data)
    {
        Assembly launcher = typeof(TocaRecomp).Assembly;
        string[] resources = launcher.GetManifestResourceNames();
        string entry = SupportPrefix + "Launch-Windows.ps1";
        if (!resources.Contains(entry, StringComparer.Ordinal))
            throw new IOException("The embedded setup script is missing.");

        // Different builds can use the same data directory without replacing each other's setup files.
        string directory = Path.Combine(data, ".launcher", launcher.ManifestModule.ModuleVersionId.ToString("N"));
        foreach (string name in resources.Where(name => name.StartsWith(SupportPrefix, StringComparison.Ordinal)))
        {
            string relative = name.Substring(SupportPrefix.Length).Replace('/', Path.DirectorySeparatorChar);
            string file = Path.Combine(directory, relative);
            using (Stream resource = launcher.GetManifestResourceStream(name))
            using (var contents = new MemoryStream())
            {
                resource.CopyTo(contents);
                WriteSupportFile(file, contents.ToArray());
            }
        }
        return Path.Combine(directory, "Launch-Windows.ps1");
    }

    private static void WriteSupportFile(string file, byte[] contents)
    {
        if (MatchesSupportFile(file, contents)) return;

        Directory.CreateDirectory(Path.GetDirectoryName(file));
        string temporary = file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllBytes(temporary, contents);
            if (File.Exists(file))
                File.Replace(temporary, file, null, true);
            else
                File.Move(temporary, file);
        }
        catch (IOException)
        {
            // Another launch may have published the same complete file while this copy was being written.
            if (!MatchesSupportFile(file, contents)) throw;
        }
        finally
        {
            File.Delete(temporary);
        }
    }

    private static bool MatchesSupportFile(string file, byte[] contents)
    {
        try
        {
            using (var saved = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete))
            {
                if (saved.Length != contents.Length) return false;
                byte[] bytes = new byte[contents.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = saved.Read(bytes, offset, bytes.Length - offset);
                    if (read == 0) return false;
                    offset += read;
                }
                return bytes.SequenceEqual(contents);
            }
        }
        catch (FileNotFoundException) { return false; }
        catch (DirectoryNotFoundException) { return false; }
    }

    private static string ReadPath(string[] args, ref int index)
    {
        string option = args[index++];
        if (index == args.Length || string.IsNullOrWhiteSpace(args[index]) || args[index].StartsWith("--", StringComparison.Ordinal))
            throw new ArgumentException(option + " requires a path.");
        return Path.GetFullPath(args[index]);
    }

    private static string Quote(string value)
    {
        if (value.Length != 0 && value.IndexOfAny(new[] { ' ', '\t', '"' }) == -1) return value;
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                slashes++;
                continue;
            }
            if (character == '"') result.Append('\\', slashes + 1);
            result.Append('\\', slashes).Append(character);
            slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
}
