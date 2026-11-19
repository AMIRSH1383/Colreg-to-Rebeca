import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtNewMethod;

/** Patch only a disposable copy of the compiler listener, never the input JAR. */
public class BuildTimingListener {
    public static void main(String[] args) throws Exception {
        ClassPool pool = new ClassPool(true);
        pool.appendClassPath(args[0]);
        CtClass listener = pool.get(
            "org.rebecalang.compiler.modelcompiler.timedrebeca.compiler.TimedRebecaListener");
        listener.addMethod(CtNewMethod.make(
            "public void exitAfter(org.rebecalang.compiler.modelcompiler.timedrebeca.compiler."
            + "TimedRebecaCompleteParser$AfterContext ctx) { ctx.e = ctx.expression().e; }", listener));
        listener.addMethod(CtNewMethod.make(
            "public void exitDeadline(org.rebecalang.compiler.modelcompiler.timedrebeca.compiler."
            + "TimedRebecaCompleteParser$DeadlineContext ctx) { ctx.e = ctx.expression().e; }", listener));
        listener.writeFile(args[1]);
    }
}
