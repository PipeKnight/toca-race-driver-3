# PS2 disc verification and archive research

## Reference disc

The reference disc is the North American PS2 release, serial `SLUS-21182`, version `1.02`, with `VMODE = NTSC`. The boot ELF entry point is `0x00120008`. PCSX2 reports game CRC `EE0618ED`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Reference ISO | 4,697,882,624 | `08c1f20904bb99067588f0aff8637f0e97cbd46d2570f4a0247245e32e5ddf29` |
| `SLUS_211.82` | 4,439,976 | `350ec46060655197f383dc15ab893231f575d99bfe03f40257ab476525b3b34e` |
| `RDH.DIR` | 65,536 | `10e4cc05d7d83b419eeb812ed8f0096bc40fe4932fa41d0b4fd88fba61704871` |
| `RDH_0.HUG` | 1,546,313,728 | |
| `RDH_1.HUG` | 1,546,352,640 | |
| `RDH_2.HUG` | 1,546,364,928 | |

From the repository root, run `java scripts/InspectDisc.java "F:/"` with Java 17 or later. Pass the drive root or an extracted directory containing `SYSTEM.CNF`. The tool reads the disc revision, hashes the ELF and directory, and reports sector counts for the three archives. It writes only to the console and can run with the disc mounted read-only. The archive checks apply to the three-file PS2 layout on the reference disc.

All 67 files visible in the DVD directory matched the lengths and SHA-256 digests of their corresponding ISO byte ranges. The visible files contain 4,662,932,399 bytes. The whole-image digest also covers 34,950,225 bytes outside those file ranges, including disc metadata and padding. The extracted-directory reader retains the file sector locations and generates the directory metadata. Its virtual DVD has SHA-256 `437b2dd9d69f92487c996f783316170ea1d1e3700407d982f40f63c2dc8bd3ed`. The mounted volume and the extracted-file copy produced the same virtual DVD digest. [Build from files](native-recompilation.md#build-directly-from-extracted-disc-files)

## PCSX2 baseline

Tested with portable PCSX2 2.8.2, the configured USA v02.00 BIOS, Fast Boot, and the automatically selected Direct3D 12 renderer at native resolution. Booting the original ISO reached the main menu and started a World Tour race. The car, track, and race HUD were visible on lap 3 of 3. The first-run flow used a local PCSX2 input replay after scripted keyboard taps failed to register as controller inputs. The replay declined formatting and continued with profile saving disabled. The check covers race startup and rendering. Race completion and saving remain untested.

Use the original ISO as the input to portable PCSX2. In this environment, PCSX2's direct access to the mounted Windows DVD device failed with Win32 error 5. Ghidra and the disc inspection tool could read files from the mounted volume. The app and emulator logs are local to the project. [PCSX2 command-line options](https://pcsx2.net/docs/advanced/cli/)

The local race-start replay is `local/pcsx2/world-tour-test.p2m2`. A shorter replay, `local/pcsx2/main-menu-analog-test.p2m2`, ends at the main menu. With the reference ISO open and an unformatted virtual memory card in slot 1, open **Tools → Input Recording → Play**, select the replay, and resume with `Space` if PCSX2 pauses. Playback restarts the virtual machine. Both replays were verified against an empty profile list and are stored with the local logs.

## Archive lookup

Ghidra 12.2 with Emotion Engine Reloaded 2.1.39 analyzed the boot ELF as `r5900:LE:32:default`. The `.mdebug.eabi64` section is empty and `.sndata` is 128 KiB. Ghidra reported a `rom0` memory-map conflict at import and skipped several VU overlay blocks during analysis. The findings below are from Emotion Engine code. Addresses are virtual addresses for the exact ELF in the table.

| Address | Observation |
| --- | --- |
| `0x005037c8` | `RDH.DIR` string. |
| `0x005037d0`, `0x005037d8` | Archive filename prefix and suffix. |
| `0x00256b10` | Initializes the archive lookup, reads the directory into a buffer, and iterates over three numbered archive names in the disc-loading path. It derives the number of physical slots by dividing the directory size by 16. |
| `0x00256860` | Receives candidate directory entries, chooses an archive and sector offset, and converts the offset to bytes using a left shift of 11. |
| `0x002566e0` | Performs path-based lookup. It indexes the directory in 16-byte units, processes each candidate before checking it, and probes within a 4,093-slot range. |
| `0x004031f8` | The transform used during lookup processes the candidate in 8-byte blocks. Its implementation and the remaining record fields require separate verification. |
| `0x00380190` | References aligned-read diagnostics that require a DWORD-aligned destination and 2 KiB-aligned offset and read size. |

The 65,536-byte directory has 4,096 physical slots. The 4,093-slot lookup range is a separate value. The number of occupied slots and the role of the three remaining slots are unverified. All three `.HUG` files have sizes divisible by the 2,048-byte sector size.

The lookup callback uses byte `+0x02` of the transformed record to select an archive. It uses the 32-bit value at `+0x08` as the start sector and passes the 32-bit value at `+0x0c` as the request length. These offsets describe the record after the transform. Verify the length against a runtime read before treating it as the exact size of an extracted asset.

### Runtime archive requests

On the reference revision, an R5900 execute breakpoint at `0x00256a48` stopped just after the callback converted the sector number to a byte offset. The requested path was at `sp`, the selected transformed record was at `s1`, the computed byte offset was in the low 32 bits of `v0`, and the request length was in the low 32 bits of `a3`. In the register pane, use **Go to in Memory** to follow `sp` and `s1`. [PCSX2 debugger documentation](https://pcsx2.net/docs/advanced/debugger/)

| Requested path | Archive | Archive-relative sector | Byte offset | Request bytes |
| --- | --- | ---: | --- | ---: |
| `SKU.INI` | `RDH_1.HUG` | 80,654 | `0x09d87000` | 20 |
| `TRACKS\OSC1\SUN\TRACK.BIG` | `RDH_1.HUG` | 522,960 | `0x3fd68000` | 328,064 |

The first request was captured during startup. To capture the track request, run the local World Tour replay from its own copy in an isolated PCSX2 profile. Set an execute breakpoint at the `Track.big` open call at `0x001e1654`. When it hits, enable the breakpoint at `0x00256a48` and resume. The next stop showed the normalized track path at `sp`. The sector read from `s1 + 0x08`, multiplied by 2,048, matched the offset in `v0` for both requests. The request length identifies the archive range. Physical CD/DVD reads may span a larger aligned range.

Reading each range directly from the disc produced the following SHA-256 values.

| Requested file | SHA-256 |
| --- | --- |
| `SKU.INI` | `8c1578fdc2e7c4befeb3d0bd31443e54c74cd74d88be5a04cb62542151523c83` |
| `TRACK.BIG` | `5d084b4600dcd635b2ece7d8428716767b92c5a0a98555a464e7eb03a693890b` |

```text
java scripts/InspectDisc.java F:/ --range 1 80654 20
java scripts/InspectDisc.java F:/ --range 1 522960 328064
```

The optional range arguments are the zero-based archive index, decimal start sector, and decimal byte count. The command checks the archive bounds before reading and reports a digest of the specified range.

### Nested PS2 BIGF package

The traced track range starts with `BIGF` and has 14 directory entries. The 32-bit fields below are little-endian. The loader at `0x00380568` confirms the signature, reads the `0x24`-byte header, and consumes `count × 0x18` directory bytes. The member read routine at `0x00380190` adds the member offset to the data base before seeking.

| Package offset | Field |
| --- | --- |
| `0x00` | Four-byte `BIGF` signature. |
| `0x04` | Number of directory entries. |
| `0x08` | Data base relative to the start of the package. It is `0x180` in this sample. |
| `0x24` | Start of the directory, with `0x18` bytes per entry. |

Each directory entry contains a `0x10`-byte name field, a 32-bit member length at `+0x10`, and a 32-bit offset relative to the data base at `+0x14`. All 14 member ranges fit inside the runtime request. The `--bigf` mode lists names, package-relative offsets, and lengths from the directory without writing member payloads.

```text
java scripts/InspectDisc.java F:/ --bigf 1 522960 328064
```

The public `bigf` library describes this same 24-byte indexed directory and data-base field in other releases in the Race Driver series. Its documentation also describes a separate marker layout. The tests here cover the indexed layout on the reference PS2 disc. [Indexed BIGF implementation](https://github.com/davidslv/bigf/blob/main/lib/bigf/archive.rb)

Add the repository's `scripts/` directory to Ghidra's Script Manager and run `FindArchiveReferences.java` after auto-analysis. The equivalent headless command from the repository root is:

```text
analyzeHeadless <project-directory> <project-name> -process SLUS_211.82 -readOnly -noanalysis -scriptPath scripts -postScript FindArchiveReferences.java
```

The script reports matching strings in `.rodata`, their references, and callers of the referencing functions. Pass specific string fragments after the script name to refine the search. Keep the Ghidra project and its generated logs under `local/`.

## Track members and model-converter compatibility

The PS2 ELF references `car.p3d` from `0x001c1b98`, which passes the name to a resource lookup at `0x00388f98`. The `Track.big` and `TrackObj.big` references occur in functions `0x001e1590` and `0x001e29b8`, respectively. Both use a common open routine at `0x00380ff0`.

The 14-member `TRACK.BIG` directory has no `.p3d` member. Four candidates were checked directly from the mounted disc on Windows 11.

| Member | Package offset | Bytes | Observed content |
| --- | ---: | ---: | --- |
| `osc1.mrc` | `0x2a00` | 26,336 | Binary. Its structure and role remain unverified. |
| `osc1.msc` | `0x9100` | 248,688 | Binary. The ELF also uses this extension for sound-related paths such as `Sound\Common.msc`. The format of this specific member still needs verification. |
| `osc1.tra` | `0x45d80` | 8,328 | Sectioned text with 34 sections, including ambience and effect sections. |
| `osc1.tta` | `0x47e40` | 19,667 | Sectioned text with 49 sections, including ambience, effects, and attached envelopes. |

Pass the name of a member to `--bigf` to report its offset, size, and SHA-256. The name match ignores ASCII case. The command validates the directory and each member range before hashing the selected payload.

```text
java scripts/InspectDisc.java F:/ --bigf 1 522960 328064 osc1.tra
```

RD3_BD7sTools documents PSP `.p3d` input and PC `.px` output. The inspected upstream `Convert()` method is empty, so there is currently no conversion result to compare with the PS2 sample. The separate `car.p3d` code reference gives a candidate for a later model-format check. [RD3_BD7sTools README](https://github.com/BuilderDemo7/RD3_BD7sTools/blob/master/README.md) · [Converter source](https://github.com/BuilderDemo7/RD3_BD7sTools/blob/master/RD3_p3d2px/Program.cs#L45-L48)

### Car and track import references

The supplied `RaceDriverP3D_zm2_src.zip` contains the Win32 ZModeler 2 filter source. Its importer accepts Race Driver 3 `.p3d` version 2 and handles model nodes, meshes, vertex streams, materials, textures, and `part.map`. The archive identifies the source as proprietary Zanoza Software code. It serves as a reference for the desktop workflow. The attached forum download returned HTTP 403, so these observations come from the supplied local ZIP. [ZModeler discussion](https://www.forumzmodeler.com/viewtopic.php?t=13551&start=50)

MarekRD3's video shows a Peugeot 205, identified by the uploader as a model from Colin McRae: DiRT, being driven in Race Driver 3. The clip supplies an example of a running car mod. Its page gives no import steps or PS2 build details. [Peugeot import demo](https://www.youtube.com/watch?v=qCG6Z6cZXFk)

On the reference PS2 ELF, the vehicle-resource function has a `car.p3d` selector and also selects `part.map`, `tex.big`, `dmg.ini`, and other companion resources. The nested member lookup handles both `BIGF` and `JPAK` directories. A direct search across the three raw `.HUG` archives found no literal null-terminated `car.p3d` name.

Track conversion needs both the visual resources and the physics and race data. The 14-member PS2 Oschersleben `TRACK.BIG` inspected above contains no `.px` or `.p3d` member. Trace the separate `TrackObj.big` and collision loads before assigning any PC format to the PS2 build. Nenkai's `col.col` template uses Mac debug symbols, and LFGamer2004's track conversion notes cover collision, render meshes, and AI data as separate formats. These are comparison references for the local PS2 samples. [Collision template](https://github.com/Nenkai/010GameTemplates/blob/main/Codemasters/Race_Driver_3/HeightData_col.col.bt) · [Track conversion notes](https://github.com/LFGamer2004/ToCA-Race-Driver-3-Modding-Track-Conversion-Tools)

### Stock PS2 DTM models and Oschersleben collision

The stock Oschersleben DTM race opened `CARDATA\DTMX\DTMX.JPK` from `RDH_2.HUG` sector 187552 and reached guest frame 3720. Its 57 outer entries contain separate `.mdl` and `.msh` files for the Audi A4, Mercedes C-Class, and Vectra. The 225 inspected nested `BIGF` members contain no `.p3d` file. The runtime probe did not capture a model from the `car.p3d` selector in this race. The extracted Audi A4 files start with little-endian words `0x00bd0b78` and `0x30000000`, respectively. The ZModeler filter expects a version word of `2` followed by its own model offsets and vertex-stream table. This makes the PS2 model pair a separate reader and writer target. A disc-wide scan found 64 sector-aligned JPAKs with `CarParts.big` and matching `.mdl`/`.msh` names. The scan checked 98 model pairs and 6,904 nested `BIGF` entries in those packs and found no `.p3d` member. The extracted assets, scan report, and trace remain under `local/asset-import-trace/`.

All 22 DTM `part.map` files match the outer structure read by ZModeler: version `1`, five LODs, 320 entries per LOD, and a 6,412-byte file. This identifies reusable serialization for the part map. Whether the indices retain the same meaning with a converted model needs to be tested with the PS2 mesh.

The track trace opened `TRACKS\OSC1\SUN\TRACK.JPK` at `RDH_1.HUG` sector 516992, `DMA.JPK` at sector 517680, and `TRACK.BIG` at sector 522960. `TRACK.JPK` includes the `col.col` collision mesh and the nested `osc1.big` package with `osc1.ail` and `.aib` entries. An independent LZSS decoder recovered `lights.ini` byte for byte against the `TRACK.BIG` copy. It also recovered `rumblehigh.px`, whose header begins with `PS2M`, version 3.

The decoded `col.col` matches the header and array layout in Nenkai's template. It contains 12,565 vertices, 18,670 triangles, 320,500 bytes of cell data, and an 8,192-byte trailer. All triangle indices are within the vertex array. At guest address `0x0131b6c0`, the running game retained the same vertex data, triangle indices, and cell data byte for byte. These verified structures can guide a PS2 collision importer. [Collision template](https://github.com/Nenkai/010GameTemplates/blob/main/Codemasters/Race_Driver_3/HeightData_col.col.bt)

At `0x001e29b8`, the object loader checks whether a track JPAK is already available. It opens `TrackObj.big` through `0x00380ff0` on the fallback branch. With a JPAK available, it resolves object members through `0x001e94b8`, which passes the member to the JPAK lookup and unpacker. The normal Oschersleben trace observed the JPAK reads and no `TrackObj.big` open. The PS2 import test should target the observed package route first.

### Resource replacement and new track slots

The reference ISO places `RDH_1.HUG` at logical block 773,120. Adding the archive-relative sector 522,960 places `TRACK.BIG` at ISO byte `0x9e368000`. The 8,328-byte `osc1.tra` member starts at ISO byte `0x9e3add80`. A read directly from the ISO matched the mounted-volume inspector's SHA-256 for both the package and the member. These offsets are specific to this disc layout.

Equal-length edits to `trkinfo.ini` and `lights.ini` were tested on separate disposable copies of the ISO. The edited images kept the disc layout and boot ELF and reached the same native World Tour race. In a paired run stopped at frame 2920, both versions of the 355-byte `lights.ini` member appeared at guest EE RAM offset `0x6427dc`. Each copy in RAM matched the member from its own ISO byte-for-byte. This verifies that the runtime reads and loads an edited track resource from the disc.

The member starts at ISO byte `0x9e368340`. The edited copy set `ambient_r`, `ambient_g`, and `ambient_b` to `99`, `00`, and `00`, and the directional light's `g` and `b` values to `000`. Use the race reproduction command with `--frames 2920` and set `PS2_DUMP` to a local output file. Search the first 32 MiB of the dump for the full member and compare the original and edited runs. The source ISO was opened read-only.

The lighting edit produced identical captures at frames 3230, 3310, and 3390. The fog edit changed some pixels at 3230 but matched the baseline at 3310 and 3390. The visible effect of the edited fields remains unverified. A read-time overlay could test equal-length changes without a temporary ISO copy.

Separate resource references in the same ELF help locate the rest of a track's inputs. These are static references to trace during race loading.

| Resource name | Referencing function | Related call path |
| --- | --- | --- |
| `TrackObj.big` | `0x001e29b8` | Called by `0x001e30e8`. |
| `track.jpk` | `0x001e8e50` | Called by `0x003a1748`, which also opens `Track.big`. |
| `TrackPosEvt.ini` | `0x003a1748` | Referenced by the same track-loading function. |
| `TrackOcc.ini` | `0x0021a100` | Called by `0x0021a730`. |
| `.ai` | `0x0020d338` | Called by `0x0020dcd8`. The full archive path and file role need runtime verification. |

An indexed `BIGF` at `RDH_1.HUG` sector 80673 (ISO byte `0x68390800`) holds 80 members containing track metadata. The `osc1.ini`, `osc2.ini`, and `osc3.ini` members include `TrackID`, `HOFIndex`, and `LengthInKm`. The directory begins at package offset `0x24`, the data base is `0x7c0`, and `osc1.ini` starts at package offset `0x2f80` with a length of 160 bytes. Reading the original ISO and inspecting the extracted disc directory located the same member.

```text
java scripts/InspectDisc.java <extracted-disc-directory> --bigf 1 80673 30720 osc1.ini
```

The catalog object exposes `TrackInfo.big` and `Mods\Tracks` through adjacent methods at `0x001e9690` and `0x001e96a0`. Its callback at `0x001e96b0` sends each entry to `0x001de628` and increments a counter after parsing. The `Mods\Tracks` string provides a second loader path to investigate.

A diagnostic runner read the catalog at guest frame 15 in two reads covering nine sectors. A read-time overlay repacked the catalog within that range, preserving every stock member's contents and order, and appended a synthetic `tqa1.ini` entry. A repacked control and the extended catalog both preserved all 80 original parsed records byte for byte. The extended catalog produced an 81st record with ID `tqa1`, short name `QA Circuit`, full name `QA Catalog Circuit`, and ordinal 80. A payload starting at `0x4320` reached the callback with incomplete metadata, so the successful repack put the payload earlier in the resource. The disc was read-only. Private test data and traces are under `local/track-slot-research/`.

The Autosport Clio Cup Free Race fixture added two rounds to `rccuf.ini`, referencing stock Oschersleben (`osc1`) and the synthetic track (`tqa1`), while retaining its nine original rounds. The game's track carousel displayed **Motopark Oschersleben** and **QA Catalog Circuit** as consecutive choices. Accepting the new entry opened **Select Car**. The test reached frame 5240 with 341 card reads, zero card writes, and the same memory card SHA-256. A checkpoint replay continued through car selection and race setup to **Next Session: Race · QA Circuit · Sunny**. Screenshots are in `clio-track-selection/frames/` and `clio-track-start/frames/` under the private test data directory.

The test entry uses Oschersleben's `HOFIndex` for this menu experiment. A playable import needs separately verified record storage, preview assets, geometry, collision, checkpoints, and AI paths.
