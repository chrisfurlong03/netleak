# The question

nPrint represents each packet as its header bits, one feature per bit: 960 columns per packet for
IPv4 plus TCP, each `1`, `0`, or `-1` where the bit is absent. That representation is deliberately
generic — it lets a model find signal anywhere in the headers without hand-engineering.

It also makes leakage easy. Some of those bits describe *behaviour*: TTL, TCP window size, the
option set a stack negotiates. Others name the *host or connection*: `ipv4_src`, `ipv4_dst`,
`tcp_sprt`, `tcp_dprt`, `tcp_seq`, `tcp_ackn`. A model free to use the second group can score well
by recognising which machine produced a capture, and that ability transfers to no other network.

The OS-detection benchmark forbids those six fields. That tells us the community knows the risk
exists. What is not published is:

- how many points of reported accuracy those fields were carrying;
- whether fields the benchmark *permits* still encode host identity;
- whether the benchmark's own train/test split hides the problem, independently of the features.

The third question turned out to matter most. A random split over sessions drawn from the same
handful of capture hosts lets a model recognise a capture environment it has already seen, whatever
the feature set. We therefore vary the features and the split as two separate axes, and report both.
