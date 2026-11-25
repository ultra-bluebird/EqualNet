% SPDX-License-Identifier: MIT OR Apache-2.0
% Assertions for the MATLAB reference functions. Expected values come from an
% independent Python brute-force enumeration (agreeing with a NumPy mirror of
% the vectorized algorithm to 1e-10). This script was NOT executed in MATLAB or
% Octave by its author; a first run may expose syntax or semantic differences.
tol = 1e-9;

r = sensing_trade_reference(zeros(100, 1), 0.5, 0.2);
assert(strcmp(r.status, 'meets'));
r = sensing_trade_reference(ones(100, 1), 5.0, 0.2);
assert(strcmp(r.status, 'fails'));
r = sensing_trade_reference(zeros(29, 1), 0.5, 0.2);
assert(strcmp(r.status, 'undetermined'));
alt = repmat([0.2; -0.2], 50, 1);
r = sensing_trade_reference(alt, 0.5, 0.2);
assert(strcmp(r.status, 'meets'));
r = sensing_trade_reference(alt, 0.1, 0.2);
assert(strcmp(r.status, 'fails'));
mixed = repmat([0.5; -0.1], 50, 1);
r = sensing_trade_reference(mixed, 0.5, 0.2);
assert(strcmp(r.status, 'undetermined'));

[n, p, t] = ambient_pmf_reference(2, 2, 1);
meanN = sum(n .* p);
assert(abs(meanN) < 1e-8);
assert(abs(sum((n - meanN) .^ 2 .* p) - 4) < 1e-8);
assert(t < 1e-9);

[n, p] = ambient_pmf_reference(0.01, 0.01, 1);
r = release_linkage_reference(10, 1, n, p, 1, 0);
assert(abs(r.advantage - 0.980296695625) < tol);
r = release_linkage_reference(7, 1, n, p, 5, 0);
assert(abs(r.advantage - 0.980296695625) < tol);
r = release_linkage_reference(5, 1, n, p, 5, 0);
assert(abs(r.advantage - 0.000049011567) < tol);
r = release_linkage_reference(4, 1, n, p, 1, 5);
assert(abs(r.advantage - 0.980296695625) < tol);

[n, p] = ambient_pmf_reference(0.5, 0.5, 1);
priorO = (40:59).';
priorP = ones(20, 1) / 20;
r = release_linkage_reference(priorO, priorP, n, p, 1, 0);
assert(abs(r.advantage - 0.465759607594) < tol);
r = release_linkage_reference(priorO, priorP, n, p, 5, 0);
assert(abs(r.advantage - 0.158988555284) < tol);
r = release_linkage_reference(priorO, priorP, n, p, [5 1], [0 0]);
assert(abs(r.advantage - 0.465759607594) < tol);

[n, p] = ambient_pmf_reference(50, 50, 1);
r = release_linkage_reference(100, 1, n, p, 1, 0);
assert(abs(r.advantage - 0.039944379299) < tol);

[n, p] = ambient_pmf_reference(1, 1, 4);
r = release_linkage_reference(10, 1, n, p, 1, 0);
assert(abs(r.advantage - 0.143431781857) < tol);

threw = false;
try
    release_linkage_reference(-1, 1, [0; 1], [0.5; 0.5], 1, 0);
catch
    threw = true;
end
assert(threw);

disp('matlab_reference_checks: all checks passed');
