import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Reports the disc revision, archive layout, or a bounded archive range from a local PS2 disc. */
public class InspectDisc {
    private static final int SECTOR_SIZE = 2048;
    private static final int DIRECTORY_SLOT_SIZE = 16;
    private static final int ARCHIVE_COUNT = 3;
    private static final int BIGF_MAGIC = 0x46474942;
    private static final int BIGF_HEADER_SIZE = 0x24;
    private static final int BIGF_ENTRY_SIZE = 0x18;
    private static final int BIGF_NAME_SIZE = 0x10;
    private static final Pattern BOOT_ENTRY = Pattern.compile(
        "(?im)^BOOT2[ \\t]*=[ \\t]*cdrom0:[\\\\/]([a-z]{4}_[0-9]{3}\\.[0-9]{2});[0-9]+[ \\t]*$");

    public static void main(String[] args) throws NoSuchAlgorithmException {
        boolean listPackage = (args.length == 5 || args.length == 6) && "--bigf".equals(args[1]);
        boolean inspectRange = args.length == 5 && "--range".equals(args[1]);
        if (args.length != 1 && !inspectRange && !listPackage) {
            System.err.println("Usage: java scripts/InspectDisc.java <disc directory> [options]");
            System.err.println("  --range <archive index> <start sector> <byte count>");
            System.err.println("  --bigf  <archive index> <start sector> <byte count> [member name]");
            System.exit(2);
        }

        try {
            Path disc = Path.of(args[0]);
            if (inspectRange || listPackage) {
                String memberName = args.length == 6 ? args[5] : null;
                inspectArchiveRange(disc, Integer.parseInt(args[2]), Long.parseLong(args[3]),
                    Long.parseLong(args[4]), listPackage, memberName);
            } else {
                inspect(disc);
            }
        } catch (IOException | IllegalArgumentException error) {
            System.err.println("Disc inspection failed: " + error.getMessage());
            System.exit(1);
        }
    }

    private static void inspect(Path disc) throws IOException, NoSuchAlgorithmException {
        String config = Files.readString(disc.resolve("SYSTEM.CNF"));
        String bootFile = requireMatch(config, BOOT_ENTRY, "BOOT2");
        String version = requireMatch(config, setting("VER"), "VER");
        String videoMode = requireMatch(config, setting("VMODE"), "VMODE");
        Path executable = disc.resolve(bootFile);
        Path directory = disc.resolve("RDH.DIR");
        long executableBytes = Files.size(executable);
        long directoryBytes = alignedSize(directory, DIRECTORY_SLOT_SIZE);
        String bootHash = sha256(executable, 0, executableBytes);
        String directoryHash = sha256(directory, 0, directoryBytes);

        System.out.printf("BOOT2: %s%nVersion: %s%nVideo mode: %s%n", bootFile, version, videoMode);
        System.out.printf("%s: %d bytes, SHA-256 %s%n", bootFile, executableBytes, bootHash);
        System.out.printf("RDH.DIR: %d bytes, %d physical slots, SHA-256 %s%n",
            directoryBytes, directoryBytes / DIRECTORY_SLOT_SIZE, directoryHash);

        for (int index = 0; index < ARCHIVE_COUNT; index++) {
            Path archive = archivePath(disc, index);
            long bytes = alignedSize(archive, SECTOR_SIZE);
            System.out.printf("%s: %d bytes, %d sectors%n", archive.getFileName(), bytes, bytes / SECTOR_SIZE);
        }
    }

    private static void inspectArchiveRange(Path disc, int index, long sector, long length,
            boolean listPackage, String memberName) throws IOException, NoSuchAlgorithmException {
        if (index < 0 || index >= ARCHIVE_COUNT) {
            throw new IllegalArgumentException("Archive index must be between 0 and " + (ARCHIVE_COUNT - 1));
        }
        Path archive = archivePath(disc, index);
        long archiveBytes = alignedSize(archive, SECTOR_SIZE);
        if (sector < 0 || sector >= archiveBytes / SECTOR_SIZE) {
            throw new IllegalArgumentException("Start sector falls outside " + archive.getFileName());
        }
        long offset = sector * SECTOR_SIZE;
        if (length <= 0 || length > archiveBytes - offset) {
            throw new IllegalArgumentException("Byte count must be positive and fit inside " + archive.getFileName());
        }

        System.out.printf("%s: sector %d, byte offset %d (0x%X), length %d bytes%n",
            archive.getFileName(), sector, offset, offset, length);
        if (listPackage) {
            inspectBigf(archive, offset, length, memberName);
        } else {
            System.out.println("SHA-256: " + sha256(archive, offset, length));
        }
    }

    private static void inspectBigf(Path archive, long offset, long packageBytes, String memberName)
            throws IOException, NoSuchAlgorithmException {
        if (packageBytes < BIGF_HEADER_SIZE) {
            throw new IOException("Range is shorter than a BIGF header");
        }

        try (FileChannel input = FileChannel.open(archive)) {
            input.position(offset);
            ByteBuffer header = ByteBuffer.allocate(BIGF_HEADER_SIZE).order(ByteOrder.LITTLE_ENDIAN);
            readFully(input, header);
            if (header.getInt() != BIGF_MAGIC) {
                throw new IOException("Range does not start with a PS2 BIGF package");
            }
            long entryCount = Integer.toUnsignedLong(header.getInt());
            long dataOffset = Integer.toUnsignedLong(header.getInt());
            if (BIGF_HEADER_SIZE + entryCount * BIGF_ENTRY_SIZE > dataOffset || dataOffset > packageBytes) {
                throw new IOException("BIGF directory or data offset falls outside the package layout");
            }

            long payloadBytes = packageBytes - dataOffset;
            ByteBuffer entry = ByteBuffer.allocate(BIGF_ENTRY_SIZE).order(ByteOrder.LITTLE_ENDIAN);
            byte[] nameBytes = new byte[BIGF_NAME_SIZE];
            BigfEntry selected = null;
            System.out.printf("BIGF: %d entries, data offset 0x%X%n", entryCount, dataOffset);
            for (long index = 0; index < entryCount; index++) {
                readFully(input, entry.clear());
                entry.get(nameBytes);
                int nameLength = 0;
                while (nameLength < nameBytes.length && nameBytes[nameLength] != 0) {
                    nameLength++;
                }
                String name = new String(nameBytes, 0, nameLength, StandardCharsets.US_ASCII);
                long length = Integer.toUnsignedLong(entry.getInt());
                long relativeOffset = Integer.toUnsignedLong(entry.getInt());
                if (relativeOffset > payloadBytes || length > payloadBytes - relativeOffset) {
                    throw new IOException("BIGF entry " + index + " falls outside the requested package range");
                }

                if (memberName == null) {
                    printBigfEntry(index, dataOffset + relativeOffset, length, name);
                } else if (name.equalsIgnoreCase(memberName)) {
                    if (selected != null) {
                        throw new IOException("Requested BIGF member name is ambiguous");
                    }
                    selected = new BigfEntry(index, dataOffset + relativeOffset, length, name);
                }
            }
            if (memberName != null) {
                if (selected == null) {
                    throw new IOException("Requested member was not found in the BIGF directory");
                }
                printBigfEntry(selected.index(), selected.offset(), selected.length(), selected.name());
                System.out.println("SHA-256: " + sha256(archive, offset + selected.offset(), selected.length()));
            }
        }
    }

    private record BigfEntry(long index, long offset, long length, String name) {}

    private static void printBigfEntry(long index, long offset, long length, String name) {
        System.out.printf("%04d  0x%08X  %8d  %s%n", index, offset, length, name.replaceAll("[^ -~]", "?"));
    }

    private static void readFully(FileChannel input, ByteBuffer buffer) throws IOException {
        while (buffer.hasRemaining()) {
            if (input.read(buffer) < 0) {
                throw new IOException("Unexpected end of archive while reading the BIGF directory");
            }
        }
        buffer.flip();
    }

    private static Path archivePath(Path disc, int index) {
        return disc.resolve("RDH_" + index + ".HUG");
    }

    private static Pattern setting(String name) {
        return Pattern.compile("(?im)^" + name + "[ \\t]*=[ \\t]*([^\\s]+)[ \\t]*$");
    }

    private static String requireMatch(String config, Pattern pattern, String label) throws IOException {
        Matcher match = pattern.matcher(config);
        if (!match.find()) {
            throw new IOException("Missing or invalid " + label + " in SYSTEM.CNF");
        }
        return match.group(1);
    }

    private static long alignedSize(Path file, int alignment) throws IOException {
        long size = Files.size(file);
        if (!Files.isRegularFile(file) || size == 0 || size % alignment != 0) {
            throw new IOException(file.getFileName() + " must be a nonempty file aligned to " + alignment + " bytes");
        }
        return size;
    }

    private static String sha256(Path file, long offset, long length) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileChannel input = FileChannel.open(file)) {
            input.position(offset);
            ByteBuffer buffer = ByteBuffer.allocate(65536);
            long remaining = length;
            while (remaining > 0) {
                buffer.clear().limit((int) Math.min(buffer.capacity(), remaining));
                int read = input.read(buffer);
                if (read < 0) {
                    throw new IOException("Unexpected end of file in " + file.getFileName());
                }
                digest.update(buffer.flip());
                remaining -= read;
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
