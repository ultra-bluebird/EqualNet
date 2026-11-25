% SPDX-License-Identifier: MIT OR Apache-2.0
function out = sensing_trade_reference(errors, maxMeanAbsError, maxAbsBias, minTrials, z)
%SENSING_TRADE_REFERENCE Three-valued scenario status for one candidate.
%   errors: estimate minus reference, persons per trial (numeric vector).
%   Trials are treated as independent. Status is 'meets', 'fails', or
%   'undetermined'. Not executed in MATLAB or Octave by its author.
if nargin < 4, minTrials = 30; end
if nargin < 5, z = 1.645; end
assert(isnumeric(errors) && isvector(errors) && all(isfinite(errors)), 'errors');
assert(maxMeanAbsError > 0 && maxAbsBias >= 0 && minTrials >= 2 && z > 0, 'limits');
e = double(errors(:));
n = numel(e);
out.n = n;
if n < minTrials
    out.status = 'undetermined';
    return
end
a = abs(e);
mae = mean(a);
meanE = mean(e);
seA = std(a) / sqrt(n);
seE = std(e) / sqrt(n);
maeLo = mae - z * seA;
maeHi = mae + z * seA;
biasLo = abs(meanE) - z * seE;
biasHi = abs(meanE) + z * seE;
if maeLo > maxMeanAbsError || biasLo > maxAbsBias
    out.status = 'fails';
elseif maeHi <= maxMeanAbsError && biasHi <= maxAbsBias
    out.status = 'meets';
else
    out.status = 'undetermined';
end
out.meanAbsError = mae;
out.bias = meanE;
out.maeUpper = maeHi;
out.biasAbsUpper = biasHi;
end
