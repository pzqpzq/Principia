# This file is part of QOBLIB - Quantum Optimization Benchmarking Library
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

param filename := "topology_40_5.dat";

param nodes := read filename as "1n" use 1 comment "#";
param degree := read filename as "2n" use 1 comment "#";

# This formulation also takes lower and upper bounds on the diameter. 
# The default values are loose and should be tightened for good 
# practical performance. We define these
# variables for ease of redefining them through command-line.
param minDiameter := 0;
param maxDiameter := nodes;

set N := { 0..nodes-1 };
set F := { <s,t> in N * N with s < t };
set D := { 0..maxDiameter-1 };

# Diameter of the graph
var diameter integer >= minDiameter <= maxDiameter;
# Distance between nodes: 1 if there is a shortest path of length d in D
# between nodes s,t in F
var dist[F * D] binary;
# Variable for linearization of products of dist variables
var y[F * N * D] binary;

minimize DIAM : diameter;

subto diameter : forall <s,t> in F : 1 + sum <d> in D : (1 - dist[s,t,d]) <= diameter;
subto DistCalc : forall <d> in D without {maxDiameter-1} : forall <s,t> in F : dist[s,t,d+1] <= dist[s,t,d] + sum <k> in N without {s,t}: y[s,t,k,d];
subto DistLinearize : forall <d> in D without {maxDiameter-1} : forall <s,t> in F : forall <k> in N without {s,t} : y[s,t,k,d] <= dist[min(s,k),max(s,k),d] and y[s,t,k,d] <= dist[min(k,t),max(k,t),0];
subto degreeButLast : forall <s> in N without {nodes-1} : sum <t> in N without {s}: dist[min(s,t),max(s,t),0] == degree;
subto degreeLast : sum <t> in N without {nodes-1} : dist[t,nodes-1,0] == if ((nodes * degree) mod 2 == 0) then degree else degree-1 end;
