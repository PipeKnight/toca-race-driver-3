using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;

internal static class TocaRecomp
{
    private const string Version = "0.1.0-dev";

    private const string Usage =
        "Usage: TocaRecomp.exe --disc PATH [--data-dir PATH] [--setup-dir PATH]\n" +
        "                     [--windowed | --fullscreen] [--direct | --setup-only]\n" +
        "                     [--no-save] [--frame-limit COUNT]\n\n" +
        "Run TOCA Race Driver 3 for Windows 11 x64 using your PS2 disc (SLUS-21182 v1.02).\n" +
        "--disc PATH          ISO, DVD CHD, or folder containing the extracted disc files.\n" +
        "--data-dir PATH      Saves, settings, caches, and runtime logs. Defaults to the launcher folder.\n" +
        "--setup-dir PATH     Portable toolchain and build files. Defaults to setup under the data folder.\n" +
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
    }

    private static int Launch(string[] args)
    {
        string disc = null;
        string data = AppDomain.CurrentDomain.BaseDirectory;
        string setup = null;
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

        string support = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "support", "Launch-Windows.ps1");
        if (!File.Exists(support)) throw new IOException("Missing support\\Launch-Windows.ps1 next to the launcher.");
        var command = new List<string> {
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", support,
            "-Disc", disc, "-DataDirectory", data, "-SetupDirectory", setup
        };
        if (direct) command.Add("-Direct");
        if (setupOnly) command.Add("-SetupOnly");
        if (noSave) command.Add("-NoSave");
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
