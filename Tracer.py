#
# Simple tracer
#
# Assists along with IDA Pro in determining the code
# exercised by a specific functionality
# 
# Note: It uses WinAppDbg to "stalk" or "break at" all process' functions
# The callback takes care of the logging process


from winappdbg import Debug, EventHandler, HexDump, Process, CrashDump
import struct
import sys
import optparse

AUTHOR = "Carlos Garcia Prado <carlos.g.prado@gmail.com>"


# Global vars... Ugly
fd = None
searchPattern = ""
interestingFunctions = list()
logged_functions = list()


############################################################################################
def main():

    global fd, searchPattern     # To modify it
    arg_check = False
    PROG_INFO = (
             "File automatically generated by %s.\n"
             "%s\n\n"
             % (sys.argv[0], AUTHOR)
             )
    
    ############################################################################
    # Parsing arguments always SUCKS
    parser = optparse.OptionParser()
    
    parser.add_option('-n', '--noise', help = 'Records noise data', action = 'store_true', dest = 'noise')
    parser.add_option('-s', '--signal', help = 'Records signal data', action = 'store_true', dest = 'signal')
    parser.add_option('-c', '--compare', help = 'Compares signal to noise', action = 'store_true', dest = 'compare')
    parser.add_option('-a', '--argument', help = 'Search for arguments', action = 'store_true', dest = 'argument')
    parser.add_option('-w', '--search_pattern', help = 'Pattern to search for', action = 'store', type = 'string', dest = 'search_pattern')
    parser.add_option('-p', '--program', help = 'Program to record', action = 'store', type = 'string', dest = 'prog')
    parser.add_option('-f', '--funcfile', help = 'File containing all function addresses', action = 'store', type = 'string', dest = 'funcfile')
            
    (opts, args) = parser.parse_args()
        

    # Mandatory Option (except with '-c')
    if opts.prog is None and opts.compare is None:
        print "[Error] What program did you say?\n"
        parser.print_help()
        sys.exit(1)
    else:
        program_file = opts.prog
        
    # Where is the functions file?
    if opts.funcfile is None:
        if opts.compare is None:
            print "[Error] I need a file with all function addresses.\n"
            parser.print_help()
            sys.exit(1)
    else:
        address_file = opts.funcfile
    
    # Word(s) to look for?
    if opts.argument:
        if opts.search_pattern is None:
            print "[Error] I need word(s) to look for. Check the 'w' option.\n"
            parser.print_help()
            sys.exit(1)
    
    # What do you want to do?    
    if opts.noise:
        output_filename = 'noise.txt'
    elif opts.signal:
        output_filename = 'signal.txt'
    elif opts.compare:
        compare()
        generateFuncRangesFile()
        sys.exit(0)
    elif opts.argument:
        output_filename = 'argument_check.txt'
        searchPattern = opts.search_pattern
        arg_check = True
    else:
        print "[Error] You must specify an option :)\n"
        parser.print_help()
        sys.exit(1)



    fd = open(output_filename, 'w')
    
    '''
    Write some short header. 
    No more open files and thinking "what was this?"
    '''

    fd.write("Analysis of program: %s\n" % program_file)
    if opts.argument:
        fd.write("Looking for pattern: %s\n" % opts.search_pattern)
    fd.write(PROG_INFO)
    
    
    simple_debugger(address_file, program_file, arg_check)
        
    print "[info] Trace finalized."


############################################################################################
def check_args_callback(event):
    '''
    This will be called when our breakpoint is hit. Checks if our string is a parameter.
    @param event: Event information, dear Watson.
    @todo: dereference the values in registers as well {eax, ebx, ecx, esi, edi}
    '''        
    nrOfArguments = 5  # TODO: Take this parameter from IDA
    
    MAX_USERSPACE_ADDRESS = 0x7FFFFFFF
    MIN_USERSPACE_ADDRESS = 0x1000
    MAX_ARGUMENT_LEN = 100  # somehow arbitrary
    
    process = event.get_process()
    thread  = event.get_thread()
    Eip     = thread.get_pc()
    Esp     = thread.get_context()['Esp']
    stackAddress = Esp + 4
    
    for idx in xrange(nrOfArguments):
        stackAddress += idx * 4
        # Dereference at address and look for searchPattern
        # NOTE: read() returns a string, not a number (unpack does the trick)
        suspectedPointer = struct.unpack('<L', process.read(stackAddress, 4))[0]
        
        if suspectedPointer > MIN_USERSPACE_ADDRESS and suspectedPointer < MAX_USERSPACE_ADDRESS:
            try:
                possibleString = process.read(suspectedPointer, MAX_ARGUMENT_LEN) # This is already a string, cool
                if searchPattern in possibleString:
                    if Eip not in logged_functions:
                        logged_functions.append(Eip)
                        print "[*] Found! %s is the parameter nr. %d of %08x" % (searchPattern, idx + 1, Eip)
                        fd.write("[*] Found! %s is the %d parameter of %08x\n" % (searchPattern, idx + 1, Eip))
                        fd.write("%s\n" % HexDump.hexblock(possibleString, suspectedPointer))
            except KeyboardInterrupt:
                fd.close()
                sys.exit(1)
            except:
                # Access violation. Log only by debugging (huge overhead due to I/O)
                pass
            
            # Let's search for the string in UNICODE
            possibleStringU = process.peek_string(suspectedPointer, fUnicode = True)
            if searchPattern in possibleStringU:
                if searchPattern in possibleString:
                    if Eip not in logged_functions:
                        logged_functions.append(Eip)
                        print "[*] Found! %s is the parameter nr. %d of %08x" % (searchPattern, idx + 1, Eip)
                        fd.write("[*] Found! %s is the %d parameter of %08x\n" % (searchPattern, idx + 1, Eip))
                        fd.write("%s\n" % HexDump.hexblock(possibleString, suspectedPointer))
    
    


############################################################################################
def log_eip_callback(event):
    '''
    This will be called when our breakpoint is hit. It writes the current EIP.
    @param event: Event information, dough!
    '''        
    
    address = event.get_thread().get_pc()
    fd.write(HexDump.address(address) + '\n')
    
    
############################################################################################
class HitTracerEventHandler(EventHandler):
    '''
    The moment we attach to the running process the create_process method will be called.
    In this case it will set breakpoints at every function.
    @param address_file: The function containing all the addresses (from IDA)
    @param program_file: The executable's name
    '''
    
    def __init__(self, address_file, program_file, arg_check = False):
        self.address_file   = address_file
        self.program_file   = program_file
        self.arg_check      = arg_check
        
        
    def create_process(self, event):   # misleading name, also called when attaching :)
        
        # I need the process PID
        module = event.get_module()
        
        if module.match_name(self.program_file):
            pid = event.get_pid()
            
            # Read the file containing the function EAs
            f = open(self.address_file, "r")
            functionAddresses = f.readlines()
            f.close()
            
            nr_of_breakpoints = 0
            
            print "[*] Preparing breakpoints. Please wait..."
            
            for f_str in functionAddresses:
                func_start_address = int(f_str.strip().split('-')[0], 16)
                
                if self.arg_check:
                    # Sets a permanent breakpoint (hit every time)
                    event.debug.break_at(pid, func_start_address, check_args_callback)
                else:
                    # Sets a one-shot breakpoint (removed after first hit)
                    event.debug.stalk_at(pid, func_start_address, log_eip_callback)
                    
                nr_of_breakpoints += 1
            
            
            print "[Debug] Installed %d breakpoints" % nr_of_breakpoints


  
############################################################################################
def compare():
    '''
    Compares both files and filters the signal.
    It outputs to "specific_functions.txt"
    '''
    
    global interestingFunctions
    OUTPUTFILENAME = 'specific_functions.txt'
    
    f = open('noise.txt', 'r')
    noise = f.readlines()
    f.close()
    
    g = open('signal.txt', 'r')
    signal = g.readlines()
    g.close()
    
    nr_of_functions = 0
    o_file = open(OUTPUTFILENAME, 'w')
    
    for func_str in signal:
        if func_str not in noise:
            '''
            NOTE: the noise, signal and specific function files have leading zeros, since
            they are the output of HexDump.address(). The IDA Pro generated file hasn't.
            Since I want to compare this afterwards, I will lstrip() the leading zeros now.
            Moreover, the IDA Pro file outputs the hex in lowercase format :)
            '''
            interestingFunctions.append(func_str.strip().lstrip('0').lower())
            o_file.write(func_str)
            nr_of_functions += 1
    
    o_file.close()
    
    print "[*] Dumped %d unique functions to %s" % (nr_of_functions, OUTPUTFILENAME)


############################################################################################
def generateFuncRangesFile():
    '''
    It generates an additional file containing not only the
    function start addresses but the ending as well.
    This is suitable to feed a Basic Block Level tracer in order to 
    specify interesting code to trace.
    '''
    
    INPUTFILENAME   = 'function_addresses.txt'
    OUTPUTFILENAME  = 'specific_functions_intervals.txt'
    
    print "[*] Generating the function intervals file. Please wait..."
    
    try:
        # I need the original file (generated by IDA Pro)
        fd_ida = open(INPUTFILENAME, 'r')
        idaFuncInfo = fd_ida.readlines()
        fd_ida.close()
    except:
        print "[debug] Fatal. Couldn't open file: %s" % INPUTFILENAME
        sys.exit(1)
    


    out_file = open(OUTPUTFILENAME, 'w')
    
    for interval in idaFuncInfo:
        if interval.split('-')[0] in interestingFunctions:
            out_file.write(interval)
 
    out_file.close()
    
    
    print "[*] Interesting functions intervals file generated: %s" % OUTPUTFILENAME

    
############################################################################################    
def simple_debugger(address_file, program_file, arg_check):
    
    process = None
    debug = Debug(HitTracerEventHandler(address_file, program_file, arg_check))
    
    
    try:
        # Lookup currently running processes
        debug.system.scan_processes()
        
        for (process, name) in debug.system.find_processes_by_filename(program_file):
            print "[*] Found %d: %s" % (process.get_pid(), name)
            
            # Attach to it
            debug.attach(process.get_pid())
            
        if process == None:
            print "[*] Fatal. Process not found. Is it running?"
            sys.exit(1)
            
        # Wait for all debugees to finish
        debug.loop()
        
    # Cleanup actions
    finally:
        debug.stop()
        


############################################################################################
def print_logo():
    ''' It prints an old school ascii logo :) '''

    LOGO = (
            " ______   ______     ______     ______     ______     ______    \n"
            "/\__  _\ /\  == \   /\  __ \   /\  ___\   /\  ___\   /\  == \   \n"
            "\/_/\ \/ \ \  __<   \ \  __ \  \ \ \____  \ \  __\   \ \  __<   \n"
            "   \ \_\  \ \_\ \_\  \ \_\ \_\  \ \_____\  \ \_____\  \ \_\ \_\ \n"
            "    \/_/   \/_/ /_/   \/_/\/_/   \/_____/   \/_____/   \/_/ /_/ \n"
            )
    
    print "%s\n" % LOGO
    print "%s\n\n" % AUTHOR


############################################################################################

if __name__ == "__main__":
    print_logo()
    main()