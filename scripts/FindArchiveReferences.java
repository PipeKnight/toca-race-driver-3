// Locate archive-related strings and their code references in a locally imported ELF.
// @category TOCA Race Driver 3

import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.TreeSet;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;

public class FindArchiveReferences extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory memory = currentProgram.getMemory();
        MemoryBlock constants = memory.getBlock(".rodata");
        if (constants == null) {
            printerr("The program has no .rodata section. Import the PS2 ELF with the ELF loader.");
            return;
        }

        String[] terms = getScriptArgs();
        if (terms.length == 0) {
            terms = new String[] { "RDH.DIR", "RDH_", ".HUG", "Common_BigFile_Read()" };
        }

        for (String term : terms) {
            if (term.isEmpty()) {
                continue;
            }
            byte[] pattern = term.getBytes(StandardCharsets.US_ASCII);
            Address searchStart = constants.getStart();
            boolean found = false;
            while (searchStart != null && searchStart.compareTo(constants.getEnd()) <= 0) {
                monitor.checkCancelled();
                Address address = memory.findBytes(
                    searchStart, constants.getEnd(), pattern, null, true, monitor);
                if (address == null) {
                    break;
                }
                found = true;
                printReferences(term, address);
                searchStart = address.next();
            }
            if (!found) {
                println(term + " was not found in .rodata");
            }
        }
    }

    private void printReferences(String term, Address address) throws Exception {
        println(term + " at " + address);
        Set<Address> referencedFunctions = new TreeSet<>();
        Set<Address> reportedAddresses = new TreeSet<>();
        for (Reference reference : getReferencesTo(address)) {
            Address from = reference.getFromAddress();
            if (!reportedAddresses.add(from)) {
                continue;
            }
            Function function = getFunctionContaining(from);
            if (function == null) {
                println("  reference at " + from + " outside an analyzed function");
                continue;
            }
            println("  reference at " + from + " in function " + function.getEntryPoint());
            if (referencedFunctions.add(function.getEntryPoint())) {
                Set<Address> callers = new TreeSet<>();
                for (Function caller : function.getCallingFunctions(monitor)) {
                    callers.add(caller.getEntryPoint());
                }
                if (!callers.isEmpty()) {
                    println("  callers: " + callers);
                }
            }
        }
    }
}
