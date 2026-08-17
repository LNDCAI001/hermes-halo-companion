import brilliant_msg as m
names = [n for n in dir(m) if n.startswith("Tx")]
print("Tx* classes:", names)
# Look for plain text / text sprite
for n in dir(m):
    if "plain" in n.lower() or "text" in n.lower():
        print("match:", n)
