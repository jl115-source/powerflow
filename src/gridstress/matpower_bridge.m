function matpower_bridge(root, options_file, output_file)
% Independent MATPOWER execution. No pandapower solution/input matrices are read.
addpath(root);
assert(install_matpower(1, 0, 0));
assert(strcmp(mpver(), '8.1'), 'Expected MATPOWER 8.1');
cfg = jsondecode(fileread(options_file));
mpc = loadcase('case30');
mpopt = mpoption('verbose', 0, 'out.all', 0, 'exp.use_legacy_core', 1, ...
    'pf.alg', 'NR', 'pf.current_balance', 0, 'pf.v_cartesian', 0, ...
    'pf.tol', cfg.pf_tolerance, 'pf.nr.max_it', cfg.pf_max_iteration, ...
    'pf.enforce_q_lims', 0, 'opf.ac.solver', 'MIPS', 'opf.dc.solver', 'MIPS', ...
    'opf.start', 1, 'opf.violation', cfg.opf_tolerance, ...
    'mips.feastol', cfg.opf_tolerance, 'mips.gradtol', cfg.opf_tolerance, ...
    'mips.comptol', cfg.opf_tolerance, 'mips.costtol', cfg.opf_tolerance, ...
    'mips.max_it', cfg.opf_max_iteration);
output = struct('matpower_version', mpver(), 'runtime_version', version(), ...
    'native_case', mpc, 'resolved_options', mpopt);
names = {'ac_pf', 'dc_pf', 'ac_current_opf', 'ac_mva_opf', 'dc_opf'};
for k = 1:length(names)
    name = names{k};
    opt = mpopt;
    if strcmp(name, 'ac_pf')
        result = runpf(mpc, opt);
    elseif strcmp(name, 'dc_pf')
        result = rundcpf(mpc, opt);
    elseif strcmp(name, 'ac_current_opf')
        opt = mpoption(opt, 'opf.flow_lim', 'I');
        result = runopf(mpc, opt);
    elseif strcmp(name, 'ac_mva_opf')
        opt = mpoption(opt, 'opf.flow_lim', 'S');
        result = runopf(mpc, opt);
    else
        result = rundcopf(mpc, opt);
    end
    assert(result.success, ['MATPOWER failed: ', name]);
    rec = struct('success', result.success, 'bus', result.bus, ...
                 'gen', result.gen, 'branch', result.branch, 'options', opt);
    rec.cost = sum(totcost(mpc.gencost, result.gen(:, 2)));
    if isfield(result, 'f')
        rec.solver_objective = result.f;
    else
        rec.solver_objective = [];
    end
    output.runs.(name) = rec;
end
fid = fopen(output_file, 'w');
assert(fid >= 0, 'Cannot open MATPOWER output');
fprintf(fid, '%s', jsonencode(output));
fclose(fid);
end
